"""Parse allowlisted filter operators from query string.

Supports: field, field__eq, field__ne, field__gt/gte/lt/lte,
field__contains, field__startswith, field__in=a,b,c
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ColumnElement, Table, and_

from contractapi.core.errors import AppError
from contractapi.domain.models.spec import EndpointSpec


from sqlalchemy import or_


_OPS = {
    "eq": lambda col, v: col == v,
    "ne": lambda col, v: col != v,
    "gt": lambda col, v: col > v,
    "gte": lambda col, v: col >= v,
    "lt": lambda col, v: col < v,
    "lte": lambda col, v: col <= v,
    "contains": lambda col, v: col.ilike(f"%{v}%"),
    "startswith": lambda col, v: col.ilike(f"{v}%"),
    "search": lambda col, v: col.ilike(f"%{v}%"),
}


def parse_filters(
    query_params: list[tuple[str, str]],
    *,
    table: Table,
    endpoint: EndpointSpec,
    reserved: set[str],
) -> list[ColumnElement[Any]]:
    allowed_fields = set(endpoint.filters)
    allowed_ops = set(endpoint.filter_operators)
    clauses: list[ColumnElement[Any]] = []
    rejected: list[str] = []
    params = list(query_params)

    # Global search: ?q=term → OR across filter fields
    search_key = endpoint.search_param
    if search_key:
        reserved = set(reserved) | {search_key}
        q_vals = [v for k, v in params if k == search_key and v]
        if q_vals and allowed_fields:
            term = q_vals[0]
            ors = []
            for field in allowed_fields:
                if field in table.c:
                    ors.append(table.c[field].ilike(f"%{term}%"))
            if ors:
                clauses.append(or_(*ors) if len(ors) > 1 else ors[0])

    for key, value in params:
        if key in reserved:
            continue
        field, op = _split_op(key)
        if field not in allowed_fields:
            rejected.append(key)
            continue
        if op not in allowed_ops:
            rejected.append(key)
            continue
        if field not in table.c:
            rejected.append(key)
            continue
        col = table.c[field]
        if op == "in":
            values = [v for v in value.split(",") if v != ""]
            clauses.append(col.in_(values))
        else:
            clauses.append(_OPS[op](col, value))

    if rejected:
        raise AppError(
            type_="https://contractapi.dev/problems/invalid-filter",
            title="Filter not allowed",
            status=400,
            detail="Only configured filter fields/operators are accepted.",
            extensions={
                "allowed_fields": sorted(allowed_fields),
                "allowed_operators": sorted(allowed_ops),
                "rejected": rejected,
            },
        )
    return clauses


def _split_op(key: str) -> tuple[str, str]:
    if "__" in key:
        field, op = key.rsplit("__", 1)
        return field, op
    return key, "eq"


def combine(clauses: list[ColumnElement[Any]]) -> ColumnElement[Any] | None:
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return and_(*clauses)
