"""Aggregation DSL compiles to SQL endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from contractapi.application.data_api_builder import create_data_app
from contractapi.domain.models.spec import (
    AggregateConfig,
    AggregateMetric,
    AggregateOp,
    compile_aggregate_sql,
    parse_spec,
)
from contractapi.infrastructure.db.engine import create_engine_for_config
from contractapi.domain.models.spec import DatabaseConfig, DatabaseDriver


def test_compile_aggregate_sql():
    agg = AggregateConfig(
        table="orders",
        schema_name="public",
        group_by=["status"],
        metrics=[
            AggregateMetric(name="order_count", op=AggregateOp.COUNT),
            AggregateMetric(name="revenue", op=AggregateOp.SUM, field="amount"),
        ],
    )
    sql = compile_aggregate_sql(agg)
    assert 'FROM "public"."orders"' in sql
    assert 'GROUP BY "status"' in sql
    assert "COUNT(*) AS \"order_count\"" in sql
    assert 'SUM("amount") AS "revenue"' in sql


def test_parse_aggregate_endpoint_expands_sql():
    spec = parse_spec(
        {
            "database": {"url": "postgresql://x/y"},
            "app": {
                "title": "A",
                "version": "0.5.0",
                "description": "t",
                "read_only": True,
                "auth": "none",
                "api_prefix": "",
            },
            "endpoints": [
                {
                    "name": "stats",
                    "path": "/stats",
                    "aggregate": {
                        "table": "orders",
                        "group_by": ["status"],
                        "metrics": [{"name": "n", "op": "count"}],
                    },
                }
            ],
        }
    )
    ep = spec.endpoints[0]
    assert ep.is_aggregate
    assert ep.is_sql
    assert ep.fields == ["status", "n"]
    assert ep.primary_key == "status"
    assert "COUNT(*)" in (ep.sql or "")


def test_aggregate_endpoint_serves_rows():
    pytest.importorskip("duckdb")
    pytest.importorskip("duckdb_engine")
    url = "duckdb:///:memory:"
    engine = create_engine_for_config(
        DatabaseConfig(url=url, driver=DatabaseDriver.DUCKDB),
        pooled=False,
    )
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE orders (status VARCHAR, amount DOUBLE)"))
        conn.execute(text("INSERT INTO orders VALUES ('paid', 10), ('paid', 5), ('open', 3)"))

    spec = parse_spec(
        {
            "database": {"url": url, "driver": "duckdb"},
            "app": {
                "title": "A",
                "version": "0.5.0",
                "description": "t",
                "read_only": True,
                "auth": "none",
                "api_prefix": "",
            },
            "endpoints": [
                {
                    "name": "stats",
                    "path": "/stats",
                    "aggregate": {
                        "table": "orders",
                        "schema": "main",
                        "group_by": ["status"],
                        "metrics": [
                            {"name": "n", "op": "count"},
                            {"name": "revenue", "op": "sum", "field": "amount"},
                        ],
                    },
                }
            ],
        }
    )
    app = create_data_app(spec, engine=engine)
    client = TestClient(app)
    res = client.get("/stats", params={"limit": 10})
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    by_status = {row["status"]: row for row in items}
    assert by_status["paid"]["n"] == 2
    assert by_status["paid"]["revenue"] == 15
    assert by_status["open"]["n"] == 1
