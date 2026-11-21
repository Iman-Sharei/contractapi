"""Write rules of an endpoint: timestamps, default/fixed values, nested writes.

Validated here so YAML, CLI and Studio all get the same checks.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, field_validator

from contractapi.domain.models.options import HttpMethod, RelationType

if TYPE_CHECKING:
    from contractapi.domain.models.endpoint import EndpointSpec

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_NESTED_CHILDREN = 100


class TimestampsConfig(BaseModel):
    """Columns the API fills with the current time (clients cannot set them)."""

    created_at: str | None = Field(default=None, description="Set once, when a row is created")
    updated_at: str | None = Field(default=None, description="Set on create and on every update")

    @field_validator("created_at", "updated_at")
    @classmethod
    def _ident(cls, value: str | None) -> str | None:
        if value is not None and not _IDENT.match(value):
            raise ValueError(f"'{value}' is not a column name")
        return value

    def columns(self) -> list[str]:
        return [c for c in (self.created_at, self.updated_at) if c]


def _check_values(ep_name: str, label: str, values: dict[str, Any]) -> None:
    for key, value in values.items():
        if not _IDENT.match(key):
            raise ValueError(f"Endpoint '{ep_name}': {label} key '{key}' is not a column name")
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError(
                f"Endpoint '{ep_name}': {label} '{key}' must be text, a number, true/false or null"
            )


def check_write_rules(ep: EndpointSpec) -> None:
    """Validate write rules; strip API-managed columns from what clients may send."""
    _check_values(ep.name, "defaults", ep.defaults)
    _check_values(ep.name, "fixed_values", ep.fixed_values)
    managed = set(ep.fixed_values) | set(ep.timestamps.columns() if ep.timestamps else [])
    if ep.primary_key in managed:
        raise ValueError(
            f"Endpoint '{ep.name}': the primary key '{ep.primary_key}' cannot be a fixed value "
            "or timestamp"
        )
    if ep.row_level and ep.row_level.column in managed:
        raise ValueError(
            f"Endpoint '{ep.name}': '{ep.row_level.column}' is already set from the caller's "
            "token (row-level access); remove it from fixed_values/timestamps"
        )
    if managed and ep.writable_fields:
        # The API sets these; a client value would be ignored, so do not accept one.
        ep.writable_fields = [f for f in ep.writable_fields if f not in managed]

    if ep.soft_delete and ep.soft_delete.restore and HttpMethod.DELETE not in ep.methods:
        raise ValueError(
            f"Endpoint '{ep.name}': soft_delete.restore undoes a delete; allow DELETE as well"
        )

    relations = {r.name: r for r in ep.relations}
    for name in ep.nested_writes:
        rel = relations.get(name)
        if rel is None:
            raise ValueError(
                f"Endpoint '{ep.name}': nested_writes '{name}' is not one of its relations "
                f"({', '.join(relations) or 'none defined'})"
            )
        if rel.type != RelationType.ONE_TO_MANY:
            raise ValueError(
                f"Endpoint '{ep.name}': nested_writes '{name}' must be a one_to_many relation "
                "(children created together with their parent)"
            )
        if HttpMethod.POST not in ep.methods:
            raise ValueError(f"Endpoint '{ep.name}': nested_writes need POST (create) allowed")
        if ep.async_writes:
            raise ValueError(
                f"Endpoint '{ep.name}': nested_writes cannot be combined with async_writes"
            )
        if not nested_child_fields(rel):
            raise ValueError(
                f"Endpoint '{ep.name}': relation '{name}' has no fields a client could write "
                "(add columns besides its primary key and foreign key)"
            )


def nested_child_fields(rel: Any) -> list[str]:
    """Columns a client may send for a nested child: the relation's fields minus its keys."""
    return [f for f in rel.fields if f not in (rel.primary_key, rel.foreign_key)]
