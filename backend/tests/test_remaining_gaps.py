"""Remaining PRODUCT_GAPS: richer agg, warehouses, dbt, git, OIDC cookie config, GraphQL RLS."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from contractapi.application.data_api_builder import create_data_app
from contractapi.application.dbt_import import import_dbt_payload
from contractapi.application.git_browser import git_status, list_branches
from contractapi.application.graphql_facade import graphql_available, mount_graphql
from contractapi.core.config import Settings
from contractapi.domain.models.spec import (
    AggregateConfig,
    AggregateFilter,
    AggregateHaving,
    AggregateMetric,
    AggregateOp,
    AggregateWindow,
    DatabaseConfig,
    DatabaseDriver,
    WindowOp,
    compile_aggregate_sql,
    parse_spec,
)
from contractapi.infrastructure.db.engine import create_engine_for_config
from contractapi.infrastructure.security.oidc import oidc_browser_enabled
from contractapi.interfaces.http.app_factory import create_studio_app


def test_compile_aggregate_where_having_windows():
    agg = AggregateConfig(
        table="orders",
        schema_name="public",
        group_by=["status"],
        where=[AggregateFilter(field="amount", op="gt", value=0)],
        metrics=[
            AggregateMetric(name="n", op=AggregateOp.COUNT),
            AggregateMetric(name="revenue", op=AggregateOp.SUM, field="amount"),
        ],
        having=[AggregateHaving(metric="revenue", op="gte", value=10)],
        windows=[
            AggregateWindow(name="rn", op=WindowOp.ROW_NUMBER, order_by=["status"]),
        ],
    )
    sql = compile_aggregate_sql(agg)
    assert 'WHERE "amount" > 0' in sql
    assert 'HAVING SUM("amount") >= 10' in sql
    assert 'ROW_NUMBER() OVER (ORDER BY "status" ASC) AS "rn"' in sql


def test_warehouse_driver_enum_and_missing_extra():
    assert DatabaseDriver.SNOWFLAKE.value == "snowflake"
    assert DatabaseDriver.BIGQUERY.value == "bigquery"
    with pytest.raises(RuntimeError, match="snowflake"):
        create_engine_for_config(
            DatabaseConfig(url="snowflake://u:p@a/d/s", driver=DatabaseDriver.SNOWFLAKE)
        )
    with pytest.raises(RuntimeError, match="bigquery"):
        create_engine_for_config(
            DatabaseConfig(url="bigquery://proj/ds", driver=DatabaseDriver.BIGQUERY)
        )


def test_dbt_schema_and_manifest_import():
    schema = {
        "models": [
            {
                "name": "fct_orders",
                "description": "Orders fact",
                "columns": [{"name": "order_id"}, {"name": "status"}],
            }
        ]
    }
    out = import_dbt_payload(schema)
    assert out["source"] == "schema_yml"
    assert out["count"] == 1
    assert out["endpoints"][0]["name"] == "fct_orders"
    assert out["endpoints"][0]["fields"] == ["order_id", "status"]

    manifest = {
        "nodes": {
            "model.proj.dim_customer": {
                "resource_type": "model",
                "name": "dim_customer",
                "schema": "analytics",
                "columns": {"id": {}, "email": {}},
                "config": {"materialized": "table"},
            }
        }
    }
    m = import_dbt_payload(manifest)
    assert m["source"] == "manifest"
    assert m["endpoints"][0]["schema"] == "analytics"
    assert "id" in m["endpoints"][0]["fields"]


def test_git_browser_on_repo():
    root = str(Path(__file__).resolve().parents[2])
    st = git_status(root)
    assert st["repo"]
    assert st["branch"]
    br = list_branches(root)
    assert st["branch"] in br["branches"] or br["current"]


def test_studio_dbt_and_git_routes(tmp_path, monkeypatch):
    from contractapi.core.config import get_settings

    monkeypatch.setenv("SPECS_DIR", str(tmp_path / "specs"))
    get_settings.cache_clear()
    settings = get_settings()
    app = create_studio_app()
    client = TestClient(app)
    headers = {"X-API-Key": settings.studio_api_key}

    res = client.post(
        "/studio/import/dbt",
        headers=headers,
        json={"models": [{"name": "orders", "columns": [{"name": "id"}]}]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["count"] == 1

    root = str(Path(__file__).resolve().parents[2])
    res2 = client.get("/studio/git/status", headers=headers, params={"repo": root})
    assert res2.status_code == 200, res2.text
    assert "sha" in res2.json()

    res3 = client.get("/studio/oidc/config")
    assert res3.status_code == 200
    body = res3.json()
    assert "browser_login" in body
    assert body["login_path"] == "/studio/oidc/login"


def test_oidc_browser_requires_client():
    s = Settings(
        studio_oidc_issuer="https://example.com/realms/x",
        studio_oidc_client_id="",
        studio_oidc_redirect_uri="",
    )
    assert oidc_browser_enabled(s) is False
    s2 = Settings(
        studio_oidc_issuer="https://example.com/realms/x",
        studio_oidc_client_id="studio",
        studio_oidc_redirect_uri="http://localhost:8000/studio/oidc/callback",
    )
    assert oidc_browser_enabled(s2) is True


def test_graphql_row_level_claims():
    if not graphql_available():
        pytest.skip("strawberry not installed")
    pytest.importorskip("duckdb")
    pytest.importorskip("duckdb_engine")
    url = "duckdb:///:memory:"
    engine = create_engine_for_config(
        DatabaseConfig(url=url, driver=DatabaseDriver.DUCKDB),
        pooled=False,
    )
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE docs (id INTEGER, owner VARCHAR, title VARCHAR)"))
        conn.execute(text("INSERT INTO docs VALUES (1, 'alice', 'A'), (2, 'bob', 'B')"))

    spec = parse_spec(
        {
            "database": {"url": url, "driver": "duckdb"},
            "app": {
                "title": "GQL",
                "version": "0.5.0",
                "description": "t",
                "read_only": True,
                "auth": "none",
                "api_prefix": "",
            },
            "endpoints": [
                {
                    "name": "docs",
                    "path": "/docs",
                    "table": "docs",
                    "schema": "main",
                    "methods": ["GET"],
                    "primary_key": "id",
                    "fields": ["id", "owner", "title"],
                    "row_level": {"column": "owner", "claim": "sub", "required": True},
                }
            ],
        }
    )
    from fastapi import FastAPI

    app = FastAPI()
    mount_graphql(app, engine, spec)
    client = TestClient(app)

    missing = client.post(
        "/graphql",
        json={"query": '{ endpoint(name: "docs", limit: 10) }'},
    )
    assert missing.status_code == 200
    assert missing.json().get("errors")

    ok = client.post(
        "/graphql",
        json={
            "query": (
                "query ($c: JSON) { endpoint(name: \"docs\", limit: 10, claims: $c) }"
            ),
            "variables": {"c": {"sub": "alice"}},
        },
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert not body.get("errors"), body
    rows = body["data"]["endpoint"]
    assert len(rows) == 1
    assert rows[0]["owner"] == "alice"


def test_aggregate_richer_serves_on_duckdb():
    pytest.importorskip("duckdb")
    pytest.importorskip("duckdb_engine")
    url = "duckdb:///:memory:"
    engine = create_engine_for_config(
        DatabaseConfig(url=url, driver=DatabaseDriver.DUCKDB),
        pooled=False,
    )
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE orders (status VARCHAR, amount DOUBLE)"))
        conn.execute(
            text("INSERT INTO orders VALUES ('paid', 10), ('paid', 5), ('open', 1), ('paid', 0)")
        )

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
                        "where": [{"field": "amount", "op": "gt", "value": 0}],
                        "metrics": [
                            {"name": "n", "op": "count"},
                            {"name": "revenue", "op": "sum", "field": "amount"},
                        ],
                        "having": [{"metric": "revenue", "op": "gte", "value": 10}],
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
    assert len(items) == 1
    assert items[0]["status"] == "paid"
    assert items[0]["revenue"] == 15
