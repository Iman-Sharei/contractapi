"""Convert dbt models / manifest nodes into contractapi endpoint drafts."""

from __future__ import annotations

import re
from typing import Any

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SLUG = re.compile(r"[^a-z0-9]+")


def _slug(name: str) -> str:
    s = _SLUG.sub("_", name.lower()).strip("_")
    return s or "model"


def _safe_ident(name: str, fallback: str) -> str:
    if _IDENT.match(name):
        return name
    return fallback


def endpoint_from_dbt_model(
    *,
    name: str,
    schema: str = "public",
    columns: list[str] | None = None,
    description: str | None = None,
    materialization: str | None = None,
    database: str | None = None,
) -> dict[str, Any]:
    """
    Build a read-only table endpoint draft from a dbt model description.

    Prefer schema.yml columns; otherwise fields stay empty for Studio pick.
    """
    slug = _slug(name)
    table = _safe_ident(name, slug)
    schema_name = _safe_ident(schema or "public", "public")
    fields = [c for c in (columns or []) if _IDENT.match(c)]
    pk = fields[0] if fields else "id"
    ep: dict[str, Any] = {
        "name": slug,
        "path": f"/{slug}",
        "table": table,
        "schema": schema_name,
        "methods": ["GET"],
        "primary_key": pk,
        "fields": fields,
        "filters": fields[:8],
        "sortable": fields[:4],
        "description": description
        or f"Imported from dbt model '{name}'"
        + (f" ({materialization})" if materialization else ""),
        "pagination": {
            "enabled": True,
            "mode": "offset",
            "default_limit": 50,
            "max_limit": 500,
        },
    }
    if database:
        ep["description"] = f"{ep['description']} [db={database}]"
    return ep


def import_from_schema_yml(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    """Parse dbt schema.yml / models:[] document into endpoint drafts."""
    models: list[dict[str, Any]] = []
    if isinstance(payload, list):
        for doc in payload:
            if isinstance(doc, dict) and "models" in doc:
                models.extend(doc.get("models") or [])
    elif isinstance(payload, dict):
        models = list(payload.get("models") or [])

    out: list[dict[str, Any]] = []
    for model in models:
        if not isinstance(model, dict) or not model.get("name"):
            continue
        cols = []
        for col in model.get("columns") or []:
            if isinstance(col, dict) and col.get("name"):
                cols.append(str(col["name"]))
            elif isinstance(col, str):
                cols.append(col)
        out.append(
            endpoint_from_dbt_model(
                name=str(model["name"]),
                schema=str(model.get("schema") or model.get("config", {}).get("schema") or "public"),
                columns=cols,
                description=model.get("description"),
                materialization=(model.get("config") or {}).get("materialized"),
            )
        )
    return out


def import_from_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse dbt manifest.json nodes (models only) into endpoint drafts."""
    nodes = manifest.get("nodes") or {}
    out: list[dict[str, Any]] = []
    for node in nodes.values():
        if not isinstance(node, dict):
            continue
        if node.get("resource_type") != "model":
            continue
        name = str(node.get("name") or node.get("alias") or "")
        if not name:
            continue
        columns = list((node.get("columns") or {}).keys())
        cfg = node.get("config") or {}
        out.append(
            endpoint_from_dbt_model(
                name=name,
                schema=str(node.get("schema") or cfg.get("schema") or "public"),
                columns=columns,
                description=node.get("description"),
                materialization=cfg.get("materialized"),
                database=node.get("database"),
            )
        )
    return out


def import_dbt_payload(payload: dict[str, Any] | list[Any]) -> dict[str, Any]:
    """
    Auto-detect manifest.json vs schema.yml and return endpoint drafts.
    """
    if isinstance(payload, dict) and "nodes" in payload:
        endpoints = import_from_manifest(payload)
        source = "manifest"
    else:
        endpoints = import_from_schema_yml(payload)
        source = "schema_yml"
    return {
        "source": source,
        "count": len(endpoints),
        "endpoints": endpoints,
    }
