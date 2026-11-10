"""Aggregation DSL helpers (models live in domain.models.spec)."""

from __future__ import annotations

from typing import Any

from contractapi.domain.models.spec import (
    AggregateConfig,
    AggregateMetric,
    AggregateOp,
    compile_aggregate_sql,
    derived_aggregate_fields,
)

__all__ = [
    "AggregateConfig",
    "AggregateMetric",
    "AggregateOp",
    "compile_aggregate_sql",
    "derived_aggregate_fields",
    "aggregate_to_endpoint_patch",
]


def aggregate_to_endpoint_patch(agg: AggregateConfig | dict[str, Any]) -> dict[str, Any]:
    """Expand aggregate config into sql/fields/table for drafts / tooling."""
    cfg = agg if isinstance(agg, AggregateConfig) else AggregateConfig.model_validate(agg)
    fields = derived_aggregate_fields(cfg)
    return {
        "sql": compile_aggregate_sql(cfg),
        "fields": fields,
        "primary_key": fields[0],
        "table": cfg.table,
        "schema": cfg.schema_name,
        "sortable": list(cfg.group_by) or fields[:1],
        "filters": list(cfg.group_by),
        "methods": ["GET"],
        "writable_fields": [],
        "relations": [],
        "aggregate": cfg.model_dump(by_alias=True),
    }
