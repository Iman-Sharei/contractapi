"""Nested warehouse columns: Snowflake VARIANT/OBJECT/ARRAY, BigQuery STRUCT/RECORD/ARRAY.

The Snowflake connector returns VARIANT values as JSON *text*; we parse them so the API returns
real JSON. These columns cannot be filtered, sorted or written through the API (the warehouse
needs PARSE_JSON / typed STRUCT literals), so activation says so instead of failing per request.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Table
from sqlalchemy.types import JSON, TypeDecorator

from contractapi.core.errors import AppError
from contractapi.domain.models.spec import DatabaseDriver, EndpointSpec

NESTED_TYPE_NAMES = {"VARIANT", "OBJECT", "ARRAY", "STRUCT", "RECORD"}
_WAREHOUSES = {DatabaseDriver.SNOWFLAKE, DatabaseDriver.BIGQUERY}


class NestedJson(TypeDecorator):
    """Result type that turns JSON text into dicts/lists (dicts and lists pass through)."""

    impl = JSON
    cache_ok = True

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if isinstance(value, (str, bytes)):
            try:
                return json.loads(value)
            except ValueError:
                return value
        return value


def is_nested_type(sa_type: Any) -> bool:
    name = type(sa_type).__name__.upper()
    if name in NESTED_TYPE_NAMES:
        return True
    return str(sa_type).upper().split("<", 1)[0].split("(", 1)[0].strip() in NESTED_TYPE_NAMES


def prepare_nested_columns(table: Table, endpoint: EndpointSpec, driver: DatabaseDriver) -> list[str]:
    """Swap result types of nested columns; refuse filters/sort/writes on them. Returns their names."""
    if driver not in _WAREHOUSES:
        return []
    nested = [c.name for c in table.columns if c.name in endpoint.fields and is_nested_type(c.type)]
    blocked = {
        "filters": sorted(set(nested) & set(endpoint.filters)),
        "sorting": sorted(set(nested) & set(endpoint.sortable)),
        "writable fields": sorted(set(nested) & set(endpoint.writable_fields)),
    }
    problems = [f"{what}: {', '.join(cols)}" for what, cols in blocked.items() if cols]
    if problems:
        raise AppError(
            type_="https://contractapi.dev/problems/misconfigured",
            title="Nested column cannot be used here",
            status=400,
            detail=(
                f"Endpoint '{endpoint.name}': columns with nested data (VARIANT, OBJECT, ARRAY, "
                f"STRUCT) can only be returned, not filtered, sorted or written. Remove them from "
                f"{'; '.join(problems)}."
            ),
        )
    for name in nested:
        table.c[name].type = NestedJson()
    return nested
