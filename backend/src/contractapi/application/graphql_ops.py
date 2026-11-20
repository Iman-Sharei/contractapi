"""GraphQL data access and mutations with the same authorization as REST (row-level, RBAC, roles)."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import Column, MetaData, String, Table, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from contractapi.core.errors import AppError
from contractapi.domain.models.spec import ApiSpec, EndpointSpec
from contractapi.infrastructure.db.dialects import MSSQL, dialect_of, page_sql
from contractapi.infrastructure.db.introspect import resolve_schema

_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _quote_ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"Unsafe identifier: {name}")
    return f'"{name}"'


def _load_table(engine: Engine, ep: EndpointSpec) -> Table:
    """Reflect table when possible; otherwise build a lightweight column map."""
    metadata = MetaData()
    schema = resolve_schema(engine, ep.schema_name) if ep.schema_name else None
    if schema in {"main", "public"}:
        try:
            return Table(ep.table, metadata, autoload_with=engine)
        except SQLAlchemyError:
            metadata = MetaData()  # retry with an explicit schema below
    try:
        return Table(ep.table, metadata, schema=schema, autoload_with=engine)
    except SQLAlchemyError:
        cols = [Column(name, String) for name in ep.fields]
        return Table(ep.table, metadata, *cols, schema=schema)


def _fetch_sql_rows(
    engine: Engine,
    ep: EndpointSpec,
    limit: int,
    *,
    bind_params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    from contractapi.application.sql_endpoint import _inner_sql

    inner = _inner_sql(ep, engine)
    if not inner:
        raise ValueError(f"Endpoint '{ep.name}' has empty SQL.")
    fields_sql = ", ".join(f"q.{_quote_ident(f)}" for f in ep.fields)
    dialect = dialect_of(engine)
    order = f" ORDER BY q.{_quote_ident(ep.primary_key)}" if dialect == MSSQL else ""
    sql = text(f"SELECT {fields_sql} FROM ({inner}) AS q{order}{page_sql(dialect, offset=False)}")
    params: dict[str, Any] = {"_limit": limit}
    # Apply declared sql_params defaults / provided binds only.
    provided = bind_params or {}
    for p in ep.sql_params:
        if p.name in provided:
            params[p.name] = provided[p.name]
        elif p.required and p.default is None:
            raise ValueError(f"Missing required SQL param '{p.name}'.")
        elif p.default is not None:
            params[p.name] = p.default
    from contractapi.application.sql_endpoint import begin_read_only

    with engine.connect() as conn:
        begin_read_only(conn)
        rows = conn.execute(sql, params).mappings().all()
    return [{k: _jsonable(v) for k, v in dict(r).items()} for r in rows]


def _claim_value(principal: dict[str, Any], claim: str) -> Any:
    """Same lookup as REST row-level: verified token claims first, then principal fields."""
    value = (principal.get("claims") or {}).get(claim)
    return principal.get(claim) if value is None else value


def _effective_roles(principal: dict[str, Any], requested: list[str] | None) -> list[str]:
    """Token roles, optionally narrowed by the client — never widened."""
    own = [str(r) for r in (principal.get("roles") or [])]
    if not requested:
        return own
    return [r for r in own if r in set(requested)]


def _row_level_missing(ep: EndpointSpec) -> AppError:
    return AppError(
        type_="https://contractapi.dev/problems/forbidden",
        title="Forbidden",
        status=403,
        detail=f"Missing claim '{ep.row_level.claim}' for row-level access on '{ep.name}'.",
    )


def _security_sql(
    ep: EndpointSpec, principal: dict[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    """Soft-delete + row-level clauses for GraphQL table reads (REST parity)."""
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if ep.soft_delete and ep.soft_delete.column:
        clauses.append(f"{_quote_ident(ep.soft_delete.column)} IS NULL")
    if ep.row_level and ep.row_level.column:
        value = _claim_value(principal, ep.row_level.claim)
        if value is None and ep.row_level.required:
            raise _row_level_missing(ep)
        if value is not None:
            clauses.append(f"{_quote_ident(ep.row_level.column)} = :_rl_claim")
            params["_rl_claim"] = value
    return clauses, params


def _fetch_rows(
    engine: Engine,
    ep: EndpointSpec,
    limit: int,
    *,
    bind_params: dict[str, Any] | None = None,
    principal: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, ep.pagination.max_limit))
    if ep.is_sql:
        return _fetch_sql_rows(engine, ep, limit, bind_params=bind_params)
    sec_clauses, sec_params = _security_sql(ep, principal or {})
    fields_sql = ", ".join(_quote_ident(f) for f in ep.fields)
    schema = resolve_schema(engine, ep.schema_name) if ep.schema_name else None
    if schema and schema not in {"main", ""}:
        table_sql = f"{_quote_ident(schema)}.{_quote_ident(ep.table)}"
    else:
        table_sql = _quote_ident(ep.table)
    where = f" WHERE {' AND '.join(sec_clauses)}" if sec_clauses else ""
    dialect = dialect_of(engine)
    order = f" ORDER BY {_quote_ident(ep.primary_key)}" if dialect == MSSQL else ""
    sql = text(f"SELECT {fields_sql} FROM {table_sql}{where}{order}{page_sql(dialect, offset=False)}")
    params = {"_limit": limit, **sec_params}
    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()
    return [{k: _jsonable(v) for k, v in dict(r).items()} for r in rows]


def _apply_rbac(
    spec: ApiSpec,
    ep: EndpointSpec,
    rows: list[dict[str, Any]],
    roles: list[str],
) -> list[dict[str, Any]]:
    """Match REST `_visible_fields` when app.rbac is configured."""
    allowed = spec.rbac_fields_for(ep.name, roles)
    if allowed is None:
        return rows
    keep = set(allowed) | {ep.primary_key} | {r.name for r in ep.relations}
    return [{k: v for k, v in row.items() if k in keep} for row in rows]


def _jsonable(value: Any) -> Any:
    """Same value format as REST (ISO dates, numbers for decimals, text UUIDs)."""
    from contractapi.application.data_api.common import _serialize

    out = _serialize(value)
    if out is None or isinstance(out, (bool, int, float, str, list, dict)):
        return out
    return str(out)
