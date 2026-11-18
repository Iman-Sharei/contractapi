"""Query-string filters and typed params for SQL endpoints (bound parameters only)."""

from __future__ import annotations

import re
from typing import Any

from fastapi import Request

from contractapi.application.exports import (  # noqa: F401 — moved; re-exported for existing imports
    _csv_response,
    _ndjson_response,
    _parquet_response,
)
from contractapi.application.query_filters import escape_like
from contractapi.core.errors import AppError
from contractapi.domain.models.spec import EndpointSpec

_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _quote_ident(name: str) -> str:
    if not _IDENT.match(name):
        raise AppError(
            type_="https://contractapi.dev/problems/misconfigured",
            title="Misconfigured",
            status=500,
            detail=f"Unsafe identifier: {name}",
        )
    return f'"{name}"'


def _build_where(
    request: Request,
    endpoint: EndpointSpec,
    *,
    reserved: set[str],
) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    allowed_fields = set(endpoint.filters)
    allowed_ops = set(endpoint.filter_operators)
    idx = 0
    for key, value in request.query_params.multi_items():
        if key in reserved:
            continue
        if "__" in key:
            field, op = key.rsplit("__", 1)
        else:
            field, op = key, "eq"
        if field not in allowed_fields or op not in allowed_ops:
            raise AppError(
                type_="https://contractapi.dev/problems/invalid-filter",
                title="Filter not allowed",
                status=400,
                detail="Only configured filter fields/operators are accepted.",
                extensions={"rejected": key},
            )
        col = f"q.{_quote_ident(field)}"
        pname = f"p{idx}"
        idx += 1
        if op == "eq":
            clauses.append(f"{col} = :{pname}")
            params[pname] = value
        elif op == "ne":
            clauses.append(f"{col} <> :{pname}")
            params[pname] = value
        elif op == "gt":
            clauses.append(f"{col} > :{pname}")
            params[pname] = value
        elif op == "gte":
            clauses.append(f"{col} >= :{pname}")
            params[pname] = value
        elif op == "lt":
            clauses.append(f"{col} < :{pname}")
            params[pname] = value
        elif op == "lte":
            clauses.append(f"{col} <= :{pname}")
            params[pname] = value
        elif op == "contains":
            clauses.append(f"CAST({col} AS TEXT) ILIKE :{pname} ESCAPE '\\'")
            params[pname] = f"%{escape_like(value)}%"
        elif op == "startswith":
            clauses.append(f"CAST({col} AS TEXT) ILIKE :{pname} ESCAPE '\\'")
            params[pname] = f"{escape_like(value)}%"
        elif op == "in":
            values = [v for v in value.split(",") if v != ""]
            placeholders = []
            for j, v in enumerate(values):
                pn = f"{pname}_{j}"
                placeholders.append(f":{pn}")
                params[pn] = v
            clauses.append(f"{col} IN ({', '.join(placeholders)})")
        else:
            raise AppError(
                type_="https://contractapi.dev/problems/invalid-filter",
                title="Filter not allowed",
                status=400,
                detail=f"Unknown operator {op}",
            )
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def bind_sql_params(endpoint: EndpointSpec, request: Request) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for param in endpoint.sql_params:
        raw = request.query_params.get(param.name)
        if raw is None or raw == "":
            if param.required and param.default is None:
                raise AppError(
                    type_="https://contractapi.dev/problems/validation-error",
                    title="Validation failed",
                    status=422,
                    detail=f"Missing required SQL param '{param.name}'.",
                )
            if param.default is not None:
                out[param.name] = param.default
            continue
        try:
            if param.type == "int":
                out[param.name] = int(raw)
            elif param.type == "float":
                out[param.name] = float(raw)
            elif param.type == "bool":
                out[param.name] = raw.lower() in {"1", "true", "yes", "on"}
            else:
                out[param.name] = raw
        except ValueError as exc:
            expected = {"int": "an integer (e.g. 42)", "float": "a number (e.g. 9.5)"}[param.type]
            raise AppError(
                type_="https://contractapi.dev/problems/validation-error",
                title="Validation failed",
                status=422,
                detail=f"SQL param '{param.name}' must be {expected}.",
            ) from exc
    return out
