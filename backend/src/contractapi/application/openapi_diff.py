"""Lightweight OpenAPI diff for CI / swagger-diff-ui integration."""

from __future__ import annotations

from typing import Any


def diff_openapi(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compare paths+methods+schema property sets. Returns NEW/UPDATE/DELETE ops."""

    before_ops = _index_operations(before)
    after_ops = _index_operations(after)

    added = sorted(set(after_ops) - set(before_ops))
    removed = sorted(set(before_ops) - set(after_ops))
    common = sorted(set(before_ops) & set(after_ops))

    updated: list[dict[str, Any]] = []
    for key in common:
        b_props = before_ops[key].get("properties", set())
        a_props = after_ops[key].get("properties", set())
        added_fields = sorted(a_props - b_props)
        removed_fields = sorted(b_props - a_props)
        if added_fields or removed_fields:
            updated.append(
                {
                    "operation": key,
                    "added_fields": added_fields,
                    "removed_fields": removed_fields,
                    "breaking": bool(removed_fields),
                }
            )

    breaking = bool(removed) or any(u["breaking"] for u in updated)
    return {
        "added": [{"operation": k, "change": "NEW"} for k in added],
        "removed": [{"operation": k, "change": "DELETE"} for k in removed],
        "updated": updated,
        "breaking": breaking,
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "updated": len(updated),
        },
        # Compatible payload shape for swagger-diff style UIs
        "changes": [
            *[{"path": k.split(" ", 1)[1], "method": k.split(" ", 1)[0], "type": "NEW"} for k in added],
            *[
                {"path": k.split(" ", 1)[1], "method": k.split(" ", 1)[0], "type": "DELETE"}
                for k in removed
            ],
            *[
                {
                    "path": u["operation"].split(" ", 1)[1],
                    "method": u["operation"].split(" ", 1)[0],
                    "type": "UPDATE",
                    "added_fields": u["added_fields"],
                    "removed_fields": u["removed_fields"],
                    "breaking": u["breaking"],
                }
                for u in updated
            ],
        ],
    }


def _index_operations(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    paths = doc.get("paths") or {}
    out: dict[str, dict[str, Any]] = {}
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, op in methods.items():
            if method.startswith("x-") or not isinstance(op, dict):
                continue
            key = f"{method.upper()} {path}"
            props = _response_properties(doc, op)
            out[key] = {"properties": props}
    return out


def _response_properties(doc: dict[str, Any], op: dict[str, Any]) -> set[str]:
    responses = op.get("responses") or {}
    for code in ("200", "201"):
        resp = responses.get(code)
        if not isinstance(resp, dict):
            continue
        content = resp.get("content") or {}
        app_json = content.get("application/json") or {}
        schema = app_json.get("schema") or {}
        return _schema_props(doc, schema)
    return set()


def _schema_props(doc: dict[str, Any], schema: dict[str, Any]) -> set[str]:
    schema = _resolve_ref(doc, schema)
    if "properties" in schema and isinstance(schema["properties"], dict):
        return set(schema["properties"].keys())
    # unwrap list envelopes: { items: { items: {...} } } or { properties: { items: ...}}
    props = schema.get("properties")
    if isinstance(props, dict) and "items" in props:
        items_schema = props["items"]
        if isinstance(items_schema, dict):
            if items_schema.get("type") == "array":
                return _schema_props(doc, items_schema.get("items") or {})
            return _schema_props(doc, items_schema)
    if schema.get("type") == "array":
        return _schema_props(doc, schema.get("items") or {})
    return set()


def _resolve_ref(doc: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if not ref or not isinstance(ref, str):
        return schema
    # #/components/schemas/Name
    parts = ref.lstrip("#/").split("/")
    node: Any = doc
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return schema
        node = node[part]
    return node if isinstance(node, dict) else schema
