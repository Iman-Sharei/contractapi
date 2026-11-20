"""Parse allowlisted filter operators from query string.

Supports: field, field__eq, field__ne, field__gt/gte/lt/lte,
field__contains, field__startswith, field__in=a,b,c (soft alias: field_op).
Values are converted to the column's Python type, so numeric/date/uuid/bool
columns filter correctly; an unconvertible value is a 400, never a 500.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import ColumnElement, Table, Unicode, and_, cast, or_

from contractapi.core.errors import AppError
from contractapi.domain.models.spec import EndpointSpec

_LIKE_OPS = {"contains", "startswith", "search"}
_CMP = {
    "eq": lambda col, v: col == v,
    "ne": lambda col, v: col != v,
    "gt": lambda col, v: col > v,
    "gte": lambda col, v: col >= v,
    "lt": lambda col, v: col < v,
    "lte": lambda col, v: col <= v,
}
KNOWN_OPS = frozenset({*_CMP, *_LIKE_OPS, "in"})
_TRUE = {"1", "true", "yes", "on", "t", "y"}
_FALSE = {"0", "false", "no", "off", "f", "n"}


def _python_type(col: Any) -> type | None:
    try:
        return col.type.python_type
    except (NotImplementedError, AttributeError):
        return None


def is_text_column(col: Any) -> bool:
    return _python_type(col) is str


class _BadValue(Exception):  # internal signal, converted to AppError
    pass


def coerce_value(col: Any, raw: str) -> Any:
    """Convert a query-string value to the column's type (raise _BadValue if impossible)."""
    py = _python_type(col)
    try:
        if py is None or py is str:
            return raw
        if py is bool:
            low = raw.strip().lower()
            if low in _TRUE:
                return True
            if low in _FALSE:
                return False
            raise _BadValue
        if py is int:
            return int(raw)
        if py is float:
            return float(raw)
        if py is Decimal:
            return Decimal(raw)
        if py is datetime:
            return datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        if py is date:
            return date.fromisoformat(raw.strip())
        if py is time:
            return time.fromisoformat(raw.strip())
        if py is uuid.UUID:
            return uuid.UUID(raw)
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise _BadValue from exc
    return raw


def _expected(col: Any) -> str:
    py = _python_type(col)
    return {
        int: "an integer (e.g. 42)",
        float: "a number (e.g. 9.5)",
        Decimal: "a number (e.g. 9.50)",
        bool: "true or false",
        datetime: "an ISO date-time (e.g. 2026-01-31T12:00:00Z)",
        date: "an ISO date (e.g. 2026-01-31)",
        time: "a time (e.g. 13:45)",
        uuid.UUID: "a UUID",
    }.get(py, "a valid value")


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _like(col: Any, op: str, value: str) -> ColumnElement[Any]:
    # Unicode(4000): a bare VARCHAR cast is only 30 characters on SQL Server.
    target = col if is_text_column(col) else cast(col, Unicode(4000))
    term = escape_like(value)
    pattern = f"{term}%" if op == "startswith" else f"%{term}%"
    return target.ilike(pattern, escape="\\")


def parse_filters(
    query_params: list[tuple[str, str]],
    *,
    table: Table,
    endpoint: EndpointSpec,
    reserved: set[str],
    visible: set[str] | None = None,
) -> list[ColumnElement[Any]]:
    """Build WHERE clauses. `visible` limits filters to fields the caller may see (RBAC)."""
    allowed_fields = set(endpoint.filters)
    if visible is not None:
        allowed_fields &= visible
    allowed_ops = set(endpoint.filter_operators)
    clauses: list[ColumnElement[Any]] = []
    rejected: list[str] = []
    bad_values: list[dict[str, str]] = []
    params = list(query_params)

    # Global search: ?q=term → OR of case-insensitive contains across text filter fields
    search_key = endpoint.search_param
    if search_key:
        reserved = set(reserved) | {search_key}
        q_vals = [v for k, v in params if k == search_key and v]
        if q_vals:
            ors = [
                _like(table.c[f], "contains", q_vals[0])
                for f in sorted(allowed_fields)
                if f in table.c and is_text_column(table.c[f])
            ]
            if ors:
                clauses.append(or_(*ors) if len(ors) > 1 else ors[0])

    for key, value in params:
        if key in reserved:
            continue
        field, op = (key, "eq") if key in allowed_fields else _split_op(key)
        if field not in allowed_fields or op not in allowed_ops or field not in table.c:
            rejected.append(key)
            continue
        col = table.c[field]
        try:
            if op == "in":
                values = [coerce_value(col, v) for v in value.split(",") if v != ""]
                clauses.append(col.in_(values))
            elif op in _LIKE_OPS:
                clauses.append(_like(col, op, value))
            else:
                clauses.append(_CMP[op](col, coerce_value(col, value)))
        except _BadValue:
            bad_values.append({"param": key, "value": value, "expected": _expected(col)})

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
    if bad_values:
        first = bad_values[0]
        raise AppError(
            type_="https://contractapi.dev/problems/invalid-filter",
            title="Invalid filter value",
            status=400,
            detail=f"'{first['param']}' must be {first['expected']}.",
            extensions={"invalid": bad_values},
        )
    return clauses


def _split_op(key: str) -> tuple[str, str]:
    """Split query key into (field, op). Prefer Django-style field__op; also accept field_op."""
    if "__" in key:
        field, op = key.rsplit("__", 1)
        return field, op
    # Soft alias: name_contains → (name, contains) when the suffix is a known operator.
    if "_" in key:
        field, maybe_op = key.rsplit("_", 1)
        if field and maybe_op in KNOWN_OPS:
            return field, maybe_op
    return key, "eq"


def combine(clauses: list[ColumnElement[Any]]) -> ColumnElement[Any] | None:
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return and_(*clauses)
