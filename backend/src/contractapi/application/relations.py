"""Batch-load relations to avoid N+1 queries."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from sqlalchemy import MetaData, text
from sqlalchemy.engine import Connection, Engine

from contractapi.domain.models.spec import RelationSpec, RelationType

_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _ser(value: Any) -> Any:
    from datetime import date, datetime
    from decimal import Decimal
    from uuid import UUID

    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _q(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"Unsafe identifier: {name}")
    return f'"{name}"'


def load_relations(
    engine: Engine,
    metadata: MetaData,
    relations: list[RelationSpec],
    parents: list[dict[str, Any]],
) -> None:
    """Mutate parent dicts in-place, attaching relation payloads."""
    del metadata  # kept for call-site compatibility
    if not relations or not parents:
        for p in parents:
            for rel in relations:
                p[rel.name] = [] if rel.type == RelationType.ONE_TO_MANY else None
        return

    with engine.connect() as conn:
        for rel in relations:
            _load_one_relation(conn, rel, parents)


def _load_one_relation(
    conn: Connection,
    rel: RelationSpec,
    parents: list[dict[str, Any]],
) -> None:
    parent_keys = [p.get(rel.local_key) for p in parents if p.get(rel.local_key) is not None]
    if not parent_keys:
        for p in parents:
            p[rel.name] = [] if rel.type == RelationType.ONE_TO_MANY else None
        return

    select_fields = list(dict.fromkeys([*rel.fields, rel.foreign_key]))
    cols = ", ".join(_q(f) for f in select_fields)
    schema = rel.schema_name
    if schema and schema not in {"main", ""}:
        table_sql = f"{_q(schema)}.{_q(rel.table)}"
    else:
        table_sql = _q(rel.table)
    placeholders = ", ".join(f":k{i}" for i in range(len(parent_keys)))
    params = {f"k{i}": v for i, v in enumerate(parent_keys)}
    sql = text(
        f"SELECT {cols} FROM {table_sql} WHERE {_q(rel.foreign_key)} IN ({placeholders})"
    )
    mappings = [dict(r) for r in conn.execute(sql, params).mappings().all()]

    grouped: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for mapping in mappings:
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
