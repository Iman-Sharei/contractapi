"""Batch-load relations to avoid N+1 queries."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import MetaData, Table, select
from sqlalchemy.engine import Connection, Engine

from contractapi.domain.models.spec import RelationSpec, RelationType


def _ser(value: Any) -> Any:
    from decimal import Decimal
    from datetime import date, datetime
    from uuid import UUID

    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def load_relations(
    engine: Engine,
    metadata: MetaData,
    relations: list[RelationSpec],
    parents: list[dict[str, Any]],
) -> None:
    """Mutate parent dicts in-place, attaching relation payloads."""
    if not relations or not parents:
        for p in parents:
            for rel in relations:
                p[rel.name] = [] if rel.type == RelationType.ONE_TO_MANY else None
        return

    with engine.connect() as conn:
        for rel in relations:
            _load_one_relation(conn, metadata, rel, parents)


def _load_one_relation(
    conn: Connection,
    metadata: MetaData,
    rel: RelationSpec,
    parents: list[dict[str, Any]],
) -> None:
    table = Table(rel.table, metadata, schema=rel.schema_name, autoload_with=conn)
    # Ensure FK column is selected for grouping even if not in response fields
    select_fields = list(dict.fromkeys([*rel.fields, rel.foreign_key]))
    missing = [f for f in select_fields if f not in table.c]
    if missing:
        raise ValueError(f"Relation '{rel.name}' missing columns: {', '.join(missing)}")

    parent_keys = [p.get(rel.local_key) for p in parents if p.get(rel.local_key) is not None]
    if not parent_keys:
        for p in parents:
            p[rel.name] = [] if rel.type == RelationType.ONE_TO_MANY else None
        return

    stmt = select(*(table.c[f] for f in select_fields)).where(
        table.c[rel.foreign_key].in_(parent_keys)
    )
    rows = conn.execute(stmt).fetchall()

    grouped: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        mapping = dict(row._mapping)
        key = mapping.get(rel.foreign_key)
        item = {f: _ser(mapping.get(f)) for f in rel.fields}
        bucket = grouped[key]
        if len(bucket) < rel.max_per_parent:
            bucket.append(item)

    if rel.type == RelationType.ONE_TO_MANY:
        for p in parents:
            p[rel.name] = grouped.get(p.get(rel.local_key), [])
    else:
        for p in parents:
            items = grouped.get(p.get(rel.local_key), [])
            p[rel.name] = items[0] if items else None
