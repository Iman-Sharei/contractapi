"""Request/response models generated from an endpoint's allowlisted columns."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, create_model
from sqlalchemy import Numeric, Table

from contractapi.application.data_api.common import _model_name, _python_type
from contractapi.application.data_api.write_rules import NestedTables
from contractapi.domain.models.spec import EndpointSpec
from contractapi.domain.models.write_options import MAX_NESTED_CHILDREN, nested_child_fields


def _write_type(col: Any, decimals: str) -> Any:
    if decimals == "string" and isinstance(col.type, Numeric) and col.type.asdecimal:
        return Decimal  # accepts "12.50" or 12.5 without float rounding
    return _python_type(col.type)


def _build_write_models(
    endpoint: EndpointSpec, table: Table, *, decimals: str = "number"
) -> tuple[type[BaseModel], type[BaseModel], type[BaseModel]]:
    read_fields: dict[str, Any] = {}
    for name in endpoint.fields:
        col = table.c[name]
        py = _python_type(col.type)
        read_fields[name] = (py | None, None) if col.nullable and name != endpoint.primary_key else (py, ...)
    item = create_model(
        f"{_model_name(endpoint.name)}Item",
        __config__=ConfigDict(from_attributes=True, extra="allow"),
        **read_fields,
    )
    listing = create_model(f"{_model_name(endpoint.name)}List", items=(list[dict], ...))
    # All writable fields optional so PATCH can send partial bodies;
    # DB NOT NULL / constraints still enforced on insert/update.
    write_fields: dict[str, Any] = {}
    for name in endpoint.writable_fields:
        write_fields[name] = (_write_type(table.c[name], decimals) | None, None)
    write_model = create_model(
        f"{_model_name(endpoint.name)}Write",
        __config__=ConfigDict(extra="forbid"),
        **write_fields,
    )
    return item, listing, write_model


def _build_create_model(
    endpoint: EndpointSpec, write_model: type[BaseModel], nested: NestedTables, *, decimals: str
) -> type[BaseModel]:
    """POST body: the write model plus one list per nested relation (children of the new row)."""
    if not nested:
        return write_model
    extra: dict[str, Any] = {}
    for name, (rel, ctable) in nested.items():
        child = create_model(
            f"{_model_name(endpoint.name)}{_model_name(name)}Child",
            __config__=ConfigDict(extra="forbid"),
            **{f: (_write_type(ctable.c[f], decimals) | None, None) for f in nested_child_fields(rel)},
        )
        extra[name] = (list[child] | None, Field(default=None, max_length=MAX_NESTED_CHILDREN))
    return create_model(f"{_model_name(endpoint.name)}Create", __base__=write_model, **extra)
