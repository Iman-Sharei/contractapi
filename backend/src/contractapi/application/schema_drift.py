"""Compare a saved API with its database now: renamed/removed columns, missing tables, new columns.

A running API only notices such changes when a request hits them (409 schema-changed); this
check lets an admin find them first, from Studio.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import inspect
from sqlalchemy.exc import NoSuchTableError, SQLAlchemyError

from contractapi.application.data_api.write_rules import managed_columns
from contractapi.core.errors import AppError
from contractapi.domain.models.spec import ApiSpec, EndpointSpec
from contractapi.domain.sensitive import find_sensitive_columns
from contractapi.infrastructure.db.engine import create_engine_for_config
from contractapi.infrastructure.db.errors import safe_db_message
from contractapi.infrastructure.db.introspect import resolve_schema


def _columns(inspector: Any, engine: Any, table: str, schema: str) -> set[str] | None:
    try:
        return {c["name"] for c in inspector.get_columns(table, schema=resolve_schema(engine, schema))}
    except NoSuchTableError:
        return None


def _check_endpoint(inspector: Any, engine: Any, ep: EndpointSpec) -> dict[str, Any]:
    out: dict[str, Any] = {"name": ep.name, "table": ep.table, "missing": [], "new_columns": []}
    if ep.is_sql:
        return {**out, "table": None, "status": "skipped",
                "detail": "Custom SQL is checked when the API is made live."}
    existing = _columns(inspector, engine, ep.table, ep.schema_name)
    if existing is None:
        return {**out, "status": "missing_table",
                "detail": f"Table '{ep.table}' no longer exists (renamed or dropped)."}
    wanted = [*ep.fields, *(managed_columns(ep) if ep.allows_writes else [])]
    if ep.row_level:
        wanted.append(ep.row_level.column)
    missing = sorted({c for c in wanted if c not in existing})
    for rel in ep.relations:
        rel_cols = _columns(inspector, engine, rel.table, rel.schema_name)
        if rel_cols is None:
            missing.append(f"{rel.name} → table {rel.table}")
            continue
        missing += [f"{rel.name}.{c}" for c in sorted({*rel.fields, rel.foreign_key} - rel_cols)]
    sensitive = set(find_sensitive_columns(sorted(existing)))
    new = sorted(c for c in existing - set(wanted) if c not in sensitive)
    out.update(missing=missing, new_columns=new)
    if missing:
        return {**out, "status": "changed",
                "detail": "Remove or rename these fields in the API, then make it live again."}
    return {**out, "status": "ok", "detail": None}


def check_database_changes(spec: ApiSpec) -> dict[str, Any]:
    engine = create_engine_for_config(spec.database, pooled=False)
    try:
        inspector = inspect(engine)
        endpoints = [_check_endpoint(inspector, engine, ep) for ep in spec.endpoints]
    except SQLAlchemyError as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/database-unreachable",
            title="Database unreachable",
            status=400,
            detail=f"Could not check the database: {safe_db_message(exc)}",
        ) from exc
    finally:
        engine.dispose()
    return {
        "ok": all(e["status"] in ("ok", "skipped") for e in endpoints),
        "endpoints": endpoints,
    }
