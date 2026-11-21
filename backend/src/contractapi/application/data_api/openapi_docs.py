"""Make each generated API's OpenAPI complete enough to hand to another team.

FastAPI only sees the routes; filters, response shapes, Problem Details errors and the
auth header live in the spec. This module adds them, so /docs gets an Authorize button,
lists every filter, and client generators produce typed models that send the key.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from fastapi import FastAPI
from sqlalchemy import Numeric, Table

from contractapi.application.data_api.common import _python_type
from contractapi.domain.models.spec import ApiSpec, AuthMode, EndpointSpec, PaginationMode

PROBLEM_REF = {"$ref": "#/components/schemas/Problem"}
PROBLEM_SCHEMA = {
    "type": "object",
    "description": "Error answer (RFC 9457 Problem Details).",
    "required": ["type", "title", "status"],
    "properties": {
        "type": {"type": "string", "description": "Stable id of the problem kind"},
        "title": {"type": "string"},
        "status": {"type": "integer"},
        "detail": {"type": "string", "description": "What went wrong and what to change"},
        "instance": {"type": "string"},
        "errors": {"type": "array", "items": {}, "description": "Field errors (validation)"},
    },
    "additionalProperties": True,
}
ERROR_TEXT = {
    400: "Bad request: a filter, sort, cursor or value is not accepted",
    401: "Missing or invalid credentials",
    403: "This caller may not do this (role or row-level rule)",
    404: "Not found",
    409: "Conflict: duplicate value, record still in use, or the database changed",
    412: "The If-Match ETag no longer matches: reload and retry",
    413: "Request body too large",
    422: "Validation failed: see errors",
    429: "Rate limit exceeded: wait for Retry-After seconds",
}
TEXT_OPS = ("contains", "startswith", "search")
OP_HELP = {
    "ne": "not equal to",
    "gt": "greater than",
    "gte": "greater than or equal to",
    "lt": "less than",
    "lte": "less than or equal to",
    "contains": "contains (case-insensitive)",
    "startswith": "starts with (case-insensitive)",
    "in": "one of (comma-separated)",
    "search": "matches the search text",
}
PUBLIC_PATHS = ("/health", "/ready", "/metrics", "/auth/refresh", "/auth/revoke")


def _base_schema(column: Any, decimals: str) -> dict[str, Any]:
    sa_type = column.type
    if decimals == "string" and isinstance(sa_type, Numeric) and sa_type.asdecimal:
        return {"type": "string", "format": "decimal", "example": "12.50"}
    py = _python_type(sa_type)
    if py is bool:
        return {"type": "boolean"}
    if py is int:
        return {"type": "integer"}
    if py is float:
        return {"type": "number"}
    if py is datetime:
        return {"type": "string", "format": "date-time"}
    if py is date:
        return {"type": "string", "format": "date"}
    if py is time:
        return {"type": "string", "format": "time"}
    if py is list:
        return {"type": "array", "items": {}}
    if py is str:
        return {"type": "string"}
    return {}  # JSON / nested warehouse data: any JSON value


def column_schema(column: Any, decimals: str) -> dict[str, Any]:
    base = _base_schema(column, decimals)
    if column.nullable and base:
        return {"anyOf": [base, {"type": "null"}]}
    return base


def item_schema(endpoint: EndpointSpec, table: Table, decimals: str) -> dict[str, Any]:
    props = {f: column_schema(table.c[f], decimals) for f in endpoint.fields}
    for rel in endpoint.relations:
        props[rel.name] = {
            "description": f"Embedded {rel.name} (with ?include={rel.name})",
            "anyOf": [{"type": "array", "items": {"type": "object"}}, {"type": "object"}, {"type": "null"}],
        }
    return {
        "type": "object",
        "description": f"One {endpoint.name} row. ?fields= and role rules may leave fields out.",
        "properties": props,
    }


def page_schema(endpoint: EndpointSpec, item_ref: dict[str, str]) -> dict[str, Any]:
    props: dict[str, Any] = {
        "items": {"type": "array", "items": item_ref},
        "limit": {"type": "integer"},
        "pagination": {"type": "object", "properties": {"mode": {"type": "string"}}},
        "total": {"type": "integer", "description": "Number of matching rows"},
    }
    if endpoint.pagination.mode == PaginationMode.CURSOR:
        props["next_cursor"] = {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": "Pass as ?cursor= for the next page; null on the last page",
        }
    else:
        props["offset"] = {"type": "integer"}
    return {"type": "object", "required": ["items", "limit", "pagination"], "properties": props}


def list_parameters(endpoint: EndpointSpec, table: Table, decimals: str) -> list[dict[str, Any]]:
    """Query parameters FastAPI cannot see: filters, ?q=, ?fields=, ?format=."""
    params: list[dict[str, Any]] = []
    ops = [o for o in endpoint.filter_operators if o != "eq"]
    for field in endpoint.filters:
        schema = _base_schema(table.c[field], decimals) or {"type": "string"}
        params.append(
            {"name": field, "in": "query", "required": False, "schema": schema,
             "description": f"Rows where {field} equals this value"}
        )
        for op in ops:
            op_schema = {"type": "string"} if op in (*TEXT_OPS, "in") else schema
            params.append(
                {"name": f"{field}__{op}", "in": "query", "required": False, "schema": op_schema,
                 "description": f"Rows where {field} is {OP_HELP.get(op, op)}"}
            )
    if endpoint.search_param and endpoint.filters:
        params.append(
            {"name": endpoint.search_param, "in": "query", "required": False,
             "schema": {"type": "string"},
             "description": f"Search text in: {', '.join(endpoint.filters)}"}
        )
    params.append(
        {"name": "fields", "in": "query", "required": False, "schema": {"type": "string"},
         "description": f"Comma-separated fields to return. Allowed: {', '.join(endpoint.fields)}"}
    )
    formats = [f for f, on in (("csv", endpoint.csv_export), ("ndjson", endpoint.ndjson_export),
                               ("parquet", endpoint.parquet_export)) if on]
    if formats:
        params.append(
            {"name": "format", "in": "query", "required": False,
             "schema": {"type": "string", "enum": formats},
             "description": "Return this page as a file instead of JSON (or send an Accept header)"}
        )
    return params


def _errors(*codes: int) -> dict[str, Any]:
    return {
        str(c): {"description": ERROR_TEXT[c], "content": {"application/problem+json": {"schema": PROBLEM_REF}}}
        for c in codes
    }


def register_endpoint_docs(
    app: FastAPI, spec: ApiSpec, endpoint: EndpointSpec, table: Table, prefix: str
) -> None:
    """Record what to add to this endpoint's operations (applied when OpenAPI is built).

    Keyed by (method, path) rather than route objects: stable across FastAPI versions."""
    decimals = spec.app.decimals
    name = "".join(p.title() for p in endpoint.name.split("_"))
    item_ref = {"$ref": f"#/components/schemas/{name}"}
    schemas = app.state.openapi_schemas
    schemas[name] = item_schema(endpoint, table, decimals)
    schemas[f"{name}Page"] = page_schema(endpoint, item_ref)

    def ok(status: str, ref: dict[str, str] | None, text: str) -> dict[str, Any]:
        out: dict[str, Any] = {"description": text}
        if ref is not None:
            out["content"] = {"application/json": {"schema": ref}}
        return {status: out}

    files = {}
    if endpoint.csv_export:
        files["text/csv"] = {"schema": {"type": "string"}}
    if endpoint.ndjson_export:
        files["application/x-ndjson"] = {"schema": {"type": "string"}}
    page_ok = ok("200", {"$ref": f"#/components/schemas/{name}Page"}, "One page of rows")
    page_ok["200"]["content"].update(files)
    bulk_ref = {
        "type": "object",
        "properties": {
            "items": {"type": "array", "items": item_ref},
            "errors": {"type": "array", "items": {"type": "object", "properties": {
                "index": {"type": "integer"}, "status": {"type": "integer"}, "detail": {"type": "string"}}}},
        },
    }
    if_match = {"name": "If-Match", "in": "header", "required": False, "schema": {"type": "string"},
                "description": "ETag from a previous read; the change is refused (412) if the row changed since"}
    idem = [{"name": "Idempotency-Key", "in": "header", "required": spec.app.idempotency.required_for_writes,
             "schema": {"type": "string"},
             "description": "Any unique text; retrying with the same key never creates the row twice"}]
    idem = idem if spec.app.idempotency.enabled else []
    read_errors = (400, 401, 403, 409, 429)
    write_errors = (400, 401, 403, 409, 413, 422, 429)
    base = f"{prefix}{endpoint.path}"
    one = f"{base}/{{item_id}}"
    docs = app.state.openapi_operations
    docs[("get", base)] = {
        "responses": {**page_ok, **_errors(*read_errors)},
        "parameters": list_parameters(endpoint, table, decimals),
    }
    docs[("get", one)] = {"responses": {**ok("200", item_ref, "The row"), **_errors(*read_errors, 404)}}
    docs[("post", base)] = {
        "responses": {**ok("201", item_ref, "Created; Location points to it"), **_errors(*write_errors)},
        "parameters": idem,
    }
    docs[("post", f"{base}/bulk")] = {
        "responses": {
            "201": {"description": "All rows created", "content": {"application/json": {"schema": bulk_ref}}},
            "207": {"description": "Some rows created; see errors", "content": {"application/json": {"schema": bulk_ref}}},
            **_errors(*write_errors),
        },
        "drop": ["200"],
    }
    for method in ("patch", "put"):
        docs[(method, one)] = {
            "responses": {**ok("200", item_ref, "The updated row"), **_errors(*write_errors, 404, 412)},
            "parameters": [if_match, *idem],
        }
    docs[("delete", one)] = {
        "responses": {**ok("204", None, "Deleted"), **_errors(401, 403, 404, 409, 412, 429)},
        "parameters": [if_match, *idem],
    }
    docs[("post", f"{one}/restore")] = {
        "responses": {**ok("200", item_ref, "The restored row"), **_errors(401, 403, 404, 409, 429)}
    }


def _security(spec: ApiSpec) -> tuple[dict[str, Any], list[dict[str, list]]]:
    if spec.app.auth == AuthMode.API_KEY:
        scheme = {"ApiKey": {"type": "apiKey", "in": "header", "name": "X-API-Key",
                             "description": "Create a key in Studio → Keys & settings"}}
        return scheme, [{"ApiKey": []}]
    if spec.app.auth == AuthMode.JWT:
        scheme = {"BearerJWT": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}}
        return scheme, [{"BearerJWT": []}]
    return {}, []


def install_openapi(app: FastAPI, spec: ApiSpec) -> None:
    """Wrap app.openapi() so every build (live /openapi.json, /docs, Studio export) is complete."""
    app.state.openapi_schemas = {}
    app.state.openapi_operations = {}
    build = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = build()
        components = schema.setdefault("components", {})
        components.setdefault("schemas", {}).update({"Problem": PROBLEM_SCHEMA, **app.state.openapi_schemas})
        # FastAPI documents its own 422 shape; ours is Problem Details.
        for name in ("HTTPValidationError", "ValidationError"):
            components["schemas"].pop(name, None)
        schemes, security = _security(spec)
        if schemes:
            components["securitySchemes"] = schemes
            schema["security"] = security
        for path, ops in schema.get("paths", {}).items():
            for method, op in ops.items():
                responses = op.setdefault("responses", {})
                if "422" in responses:
                    responses["422"] = _errors(422)["422"]
                extra = app.state.openapi_operations.get((method, path), {})
                for code in extra.get("drop", []):
                    responses.pop(code, None)
                responses.update(extra.get("responses", {}))
                known = {p["name"] for p in op.get("parameters", [])}
                new = [p for p in extra.get("parameters", []) if p["name"] not in known]
                if new:
                    op["parameters"] = [*op.get("parameters", []), *new]
                if path in PUBLIC_PATHS:
                    op["security"] = []
        return schema

    app.openapi = openapi  # type: ignore[method-assign]
