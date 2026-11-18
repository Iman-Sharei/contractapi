"""Aggregation DSL: declarative GROUP BY / HAVING / window metrics compiled to a SELECT.

Identifiers are allowlisted (`_IDENT`) and quoted; literal values are escaped (`_literal`).
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class AggregateOp(str, Enum):
    COUNT = "count"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"


class AggregateMetric(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    op: AggregateOp
    field: str | None = None

    @model_validator(mode="after")
    def check_field(self) -> AggregateMetric:
        if self.op != AggregateOp.COUNT and not self.field:
            raise ValueError(f"Metric '{self.name}' ({self.op}) requires field")
        if self.field and not _IDENT.match(self.field):
            raise ValueError(f"Unsafe metric field: {self.field}")
        return self


class AggregateFilter(BaseModel):
    """Pre-aggregation WHERE clause (column op value)."""

    field: str
    op: str = "eq"  # eq|ne|gt|gte|lt|lte|in
    value: Any = None

    @model_validator(mode="after")
    def check(self) -> AggregateFilter:
        if not _IDENT.match(self.field):
            raise ValueError(f"Unsafe filter field: {self.field}")
        if self.op not in {"eq", "ne", "gt", "gte", "lt", "lte", "in"}:
            raise ValueError(f"Unsupported filter op: {self.op}")
        return self


class AggregateHaving(BaseModel):
    """Post-aggregation HAVING on a metric alias."""

    metric: str
    op: str = "gte"
    value: float | int

    @model_validator(mode="after")
    def check(self) -> AggregateHaving:
        if not _IDENT.match(self.metric):
            raise ValueError(f"Unsafe having metric: {self.metric}")
        if self.op not in {"eq", "ne", "gt", "gte", "lt", "lte"}:
            raise ValueError(f"Unsupported having op: {self.op}")
        return self


class WindowOp(str, Enum):
    ROW_NUMBER = "row_number"
    RANK = "rank"
    SUM = "sum"
    AVG = "avg"
    COUNT = "count"


class AggregateWindow(BaseModel):
    """Window function column (OVER partition/order)."""

    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    op: WindowOp
    field: str | None = None
    partition_by: list[str] = Field(default_factory=list)
    order_by: list[str] = Field(
        default_factory=list,
        description="Column names; prefix with - for DESC",
    )

    @model_validator(mode="after")
    def check(self) -> AggregateWindow:
        if self.op in {WindowOp.SUM, WindowOp.AVG} and not self.field:
            raise ValueError(f"Window '{self.name}' ({self.op}) requires field")
        if self.field and not _IDENT.match(self.field):
            raise ValueError(f"Unsafe window field: {self.field}")
        for col in self.partition_by:
            if not _IDENT.match(col):
                raise ValueError(f"Unsafe partition_by: {col}")
        for col in self.order_by:
            raw = col[1:] if col.startswith("-") else col
            if not _IDENT.match(raw):
                raise ValueError(f"Unsafe order_by: {col}")
        return self


class AggregateConfig(BaseModel):
    """Declarative aggregation — compiled to a read-only SELECT subquery."""

    table: str = Field(min_length=1)
    schema_name: str = Field(default="public", alias="schema")
    group_by: list[str] = Field(default_factory=list)
    metrics: list[AggregateMetric] = Field(min_length=1)
    where: list[AggregateFilter] = Field(default_factory=list)
    having: list[AggregateHaving] = Field(default_factory=list)
    windows: list[AggregateWindow] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def check_idents(self) -> AggregateConfig:
        if not _IDENT.match(self.table):
            raise ValueError(f"Unsafe table name: {self.table}")
        if self.schema_name and not _IDENT.match(self.schema_name):
            raise ValueError(f"Unsafe schema name: {self.schema_name}")
        for col in self.group_by:
            if not _IDENT.match(col):
                raise ValueError(f"Unsafe group_by column: {col}")
        names = [m.name for m in self.metrics] + [w.name for w in self.windows]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate aggregate metric/window names")
        clash = set(self.group_by) & set(names)
        if clash:
            raise ValueError(f"Metric/window names clash with group_by: {sorted(clash)}")
        metric_names = {m.name for m in self.metrics}
        for h in self.having:
            if h.metric not in metric_names:
                raise ValueError(f"HAVING metric '{h.metric}' not in metrics")
        return self


def _quote_agg_ident(name: str) -> str:
    return f'"{name}"'


def _agg_metric_expr(metric: AggregateMetric) -> str:
    if metric.op == AggregateOp.COUNT:
        return f"COUNT({_quote_agg_ident(metric.field)})" if metric.field else "COUNT(*)"
    if metric.op == AggregateOp.SUM:
        return f"SUM({_quote_agg_ident(metric.field)})"
    if metric.op == AggregateOp.AVG:
        return f"AVG({_quote_agg_ident(metric.field)})"
    if metric.op == AggregateOp.MIN:
        return f"MIN({_quote_agg_ident(metric.field)})"
    return f"MAX({_quote_agg_ident(metric.field)})"


def _agg_cmp(op: str, left: str, right_sql: str) -> str:
    mapping = {
        "eq": "=",
        "ne": "<>",
        "gt": ">",
        "gte": ">=",
        "lt": "<",
        "lte": "<=",
    }
    return f"{left} {mapping[op]} {right_sql}"


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    # escape single quotes
    return "'" + str(value).replace("'", "''") + "'"


def _window_expr(window: AggregateWindow) -> str:
    if window.op == WindowOp.ROW_NUMBER:
        fn = "ROW_NUMBER()"
    elif window.op == WindowOp.RANK:
        fn = "RANK()"
    elif window.op == WindowOp.COUNT:
        fn = f"COUNT({_quote_agg_ident(window.field)})" if window.field else "COUNT(*)"
    elif window.op == WindowOp.SUM:
        fn = f"SUM({_quote_agg_ident(window.field or '')})"
    else:
        fn = f"AVG({_quote_agg_ident(window.field or '')})"
    parts: list[str] = []
    if window.partition_by:
        parts.append(
            "PARTITION BY " + ", ".join(_quote_agg_ident(c) for c in window.partition_by)
        )
    if window.order_by:
        order_bits = []
        for col in window.order_by:
            if col.startswith("-"):
                order_bits.append(f"{_quote_agg_ident(col[1:])} DESC")
            else:
                order_bits.append(f"{_quote_agg_ident(col)} ASC")
        parts.append("ORDER BY " + ", ".join(order_bits))
    over = " ".join(parts)
    return f"{fn} OVER ({over})" if over else f"{fn} OVER ()"


def compile_aggregate_sql(agg: AggregateConfig) -> str:
    select_parts: list[str] = [_quote_agg_ident(c) for c in agg.group_by]
    for metric in agg.metrics:
        select_parts.append(
            f"{_agg_metric_expr(metric)} AS {_quote_agg_ident(metric.name)}"
        )
    for window in agg.windows:
        select_parts.append(
            f"{_window_expr(window)} AS {_quote_agg_ident(window.name)}"
        )
    table_sql = (
        f"{_quote_agg_ident(agg.schema_name)}.{_quote_agg_ident(agg.table)}"
        if agg.schema_name
        else _quote_agg_ident(agg.table)
    )
    sql = f"SELECT {', '.join(select_parts)} FROM {table_sql}"
    if agg.where:
        wheres: list[str] = []
        for flt in agg.where:
            col = _quote_agg_ident(flt.field)
            if flt.op == "in":
                values = flt.value if isinstance(flt.value, list) else [flt.value]
                lit = ", ".join(_literal(v) for v in values)
                wheres.append(f"{col} IN ({lit})")
            else:
                wheres.append(_agg_cmp(flt.op, col, _literal(flt.value)))
        sql += " WHERE " + " AND ".join(wheres)
    if agg.group_by:
        sql += f" GROUP BY {', '.join(_quote_agg_ident(c) for c in agg.group_by)}"
    if agg.having:
        havings: list[str] = []
        for h in agg.having:
            metric = next(m for m in agg.metrics if m.name == h.metric)
            left = _agg_metric_expr(metric)
            havings.append(_agg_cmp(h.op, left, _literal(h.value)))
        sql += " HAVING " + " AND ".join(havings)
    return sql


def derived_aggregate_fields(agg: AggregateConfig) -> list[str]:
    return [
        *agg.group_by,
        *[m.name for m in agg.metrics],
        *[w.name for w in agg.windows],
    ]
