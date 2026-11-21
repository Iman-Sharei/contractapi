"""Spec write rules shared by REST and GraphQL: timestamps, default/fixed values, nested
children, reviving soft-deleted rows. Business rules only; HTTP handling stays in writes.py."""

from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from typing import Any

from sqlalchemy import Table, and_, or_, select
from sqlalchemy.schema import UniqueConstraint

from contractapi.core.errors import AppError
from contractapi.domain.models.spec import ApiSpec, EndpointSpec, RelationSpec
from contractapi.domain.models.write_options import nested_child_fields
from contractapi.infrastructure.db.dialects import insert_returning, update_returning

VALIDATION_ERROR = "https://contractapi.dev/problems/validation-error"


def db_timezone(spec: ApiSpec) -> tzinfo:
    from zoneinfo import ZoneInfo

    return ZoneInfo(spec.database.timezone) if spec.database.timezone else timezone.utc


def now_for(table: Table, column: str, tz: tzinfo) -> datetime:
    """Current time in the form the column stores: aware for time-zone columns, otherwise the
    wall-clock time of the database's time zone (MySQL DATETIME, SQL Server datetime2)."""
    now = datetime.now(timezone.utc)
    col = table.c.get(column)
    if col is None or getattr(col.type, "timezone", False):
        return now
    return now.astimezone(tz).replace(tzinfo=None)


def managed_columns(endpoint: EndpointSpec) -> list[str]:
    cols = list(endpoint.defaults) + list(endpoint.fixed_values)
    if endpoint.timestamps:
        cols += endpoint.timestamps.columns()
    if endpoint.soft_delete:
        cols.append(endpoint.soft_delete.column)
    return cols


def missing_managed_columns(table: Table, endpoint: EndpointSpec) -> list[str]:
    return sorted({c for c in managed_columns(endpoint) if c not in table.c})


def for_create(endpoint: EndpointSpec, table: Table, payload: dict[str, Any], tz: tzinfo) -> dict[str, Any]:
    out = {k: v for k, v in endpoint.defaults.items() if k not in payload}
    out.update(payload)
    out.update(endpoint.fixed_values)
    if endpoint.timestamps:
        for col in endpoint.timestamps.columns():
            out[col] = now_for(table, col, tz)
    return out


def for_update(endpoint: EndpointSpec, table: Table, payload: dict[str, Any], tz: tzinfo) -> dict[str, Any]:
    out = {**payload, **endpoint.fixed_values}
    if endpoint.timestamps and endpoint.timestamps.updated_at:
        out[endpoint.timestamps.updated_at] = now_for(table, endpoint.timestamps.updated_at, tz)
    return out


# ---- nested children (one_to_many, created with the parent in one transaction) ----

NestedTables = dict[str, tuple[RelationSpec, Table]]


def split_nested(endpoint: EndpointSpec, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, list]]:
    """Separate child lists (relation names) from the parent's columns."""
    children = {n: payload.pop(n) for n in list(endpoint.nested_writes) if n in payload}
    for name, items in children.items():
        if items is None:
            children[name] = []
        elif not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
            raise AppError(
                type_=VALIDATION_ERROR,
                title="Validation failed",
                status=422,
                detail=f"'{name}' must be a list of objects.",
            )
    return payload, children


def _check_child(rel: RelationSpec, index: int, item: dict[str, Any]) -> None:
    allowed = set(nested_child_fields(rel))
    unknown = sorted(set(item) - allowed)
    if unknown:
        raise AppError(
            type_=VALIDATION_ERROR,
            title="Validation failed",
            status=422,
            detail=(
                f"{rel.name}[{index}]: these fields cannot be sent: {', '.join(unknown)}. "
                f"Allowed: {', '.join(sorted(allowed))}."
            ),
        )


def insert_children(
    conn: Any,
    endpoint: EndpointSpec,
    parent: dict[str, Any],
    children: dict[str, list],
    tables: NestedTables,
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    owner = endpoint.row_level.column if endpoint.row_level else None
    for name, items in children.items():
        rel, ctable = tables[name]
        rows = []
        for idx, item in enumerate(items):
            _check_child(rel, idx, item)
            values = {**item, rel.foreign_key: parent[rel.local_key]}
            if owner and owner in ctable.c and owner in parent:
                values[owner] = parent[owner]  # children belong to the parent's owner
            row = insert_returning(conn, ctable, values, rel.fields, rel.primary_key)
            rows.append(dict(row) if row is not None else values)
        out[name] = rows
    return out


# ---- soft delete: reuse values of deleted rows, restore ----


def unique_column_sets(table: Table) -> list[tuple[str, ...]]:
    sets = {tuple(c.name for c in uc.columns) for uc in table.constraints if isinstance(uc, UniqueConstraint)}
    sets |= {tuple(c.name for c in ix.columns) for ix in table.indexes if ix.unique}
    return sorted(s for s in sets if s)


def revive_deleted(
    conn: Any,
    table: Table,
    endpoint: EndpointSpec,
    payload: dict[str, Any],
    unique_sets: list[tuple[str, ...]],
) -> Any:
    """Bring back the deleted row that holds one of the payload's unique values, with the new
    values. Only rows of the same owner (row-level) qualify. None when there is no such row."""
    if not endpoint.soft_delete:
        return None
    matches = [
        and_(*(table.c[c] == payload[c] for c in cols))
        for cols in unique_sets
        if all(c in payload for c in cols)
    ]
    if not matches:
        return None
    deleted = table.c[endpoint.soft_delete.column]
    where = [deleted.isnot(None), or_(*matches)]
    if endpoint.row_level and endpoint.row_level.column in payload:
        where.append(table.c[endpoint.row_level.column] == payload[endpoint.row_level.column])
    pk = table.c[endpoint.primary_key]
    found = conn.execute(select(pk).where(and_(*where)).limit(1)).first()
    if found is None:
        return None
    values = {k: v for k, v in payload.items() if k != endpoint.primary_key}
    values[endpoint.soft_delete.column] = None
    return update_returning(conn, table, pk == found[0], values, endpoint.fields)
