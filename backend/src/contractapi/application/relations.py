"""Batch-load relations to avoid N+1 queries."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from sqlalchemy import MetaData, text
from sqlalchemy.engine import Connection, Engine

from contractapi.domain.models.spec import RelationSpec, RelationType
from contractapi.infrastructure.db.dialects import dialect_of, table_schema

_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _ser(value: Any) -> Any:
    """Same value format as the parent rows (decimals, time zone): one shared serializer."""
    from contractapi.application.data_api.common import _serialize

    return _serialize(value)


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
    schema = table_schema(dialect_of(conn), rel.schema_name, database=conn.engine.url.database)
    if schema and schema not in {"main", ""}:
        table_sql = f"{_q(schema)}.{_q(rel.table)}"
    else:
        table_sql = _q(rel.table)
    placeholders = ", ".join(f":k{i}" for i in range(len(parent_keys)))
    params: dict[str, Any] = {f"k{i}": v for i, v in enumerate(parent_keys)}
    params["_max"] = rel.max_per_parent
    where = f"{_q(rel.foreign_key)} IN ({placeholders})"
    if rel.soft_delete_column:
        where += f" AND {_q(rel.soft_delete_column)} IS NULL"
    order = _q(rel.primary_key) if rel.primary_key in rel.fields else _q(rel.foreign_key)
    # Cap rows per parent in the database (not after fetching every child row).
    sql = text(
        f"SELECT {cols} FROM ("
        f"SELECT {cols}, ROW_NUMBER() OVER (PARTITION BY {_q(rel.foreign_key)} ORDER BY {order}) "
        f"AS _ca_rn FROM {table_sql} WHERE {where}"
        f") AS _ca_rel WHERE _ca_rn <= :_max"
    )
    mappings = [dict(r) for r in conn.execute(sql, params).mappings().all()]

    grouped: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for mapping in mappings:
        key = mapping.get(rel.foreign_key)
        item = {f: _ser(mapping.get(f)) for f in rel.fields}
        grouped[key].append(item)

    if rel.type == RelationType.ONE_TO_MANY:
        for p in parents:
            p[rel.name] = grouped.get(p.get(rel.local_key), [])
    else:
        for p in parents:
            items = grouped.get(p.get(rel.local_key), [])
            p[rel.name] = items[0] if items else None
