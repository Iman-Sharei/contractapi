"""GraphQL read facade is GA — mounts when strawberry is installed."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from contractapi.application.data_api_builder import create_data_app
from contractapi.application.graphql_facade import graphql_available, mount_graphql
from contractapi.core.config import Settings
from contractapi.domain.models.spec import DatabaseConfig, DatabaseDriver, parse_spec
from contractapi.infrastructure.db.engine import create_engine_for_config


def test_graphql_not_experimental():
    assert "graphql" not in Settings(experimental="all").experimental_set


def test_graphql_available_endpoints_query():
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
        conn.execute(text("CREATE TABLE customers (id INTEGER, email VARCHAR)"))
        conn.execute(text("INSERT INTO customers VALUES (1, 'a@b.c')"))

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
                    "name": "customers",
                    "path": "/customers",
                    "table": "customers",
                    "schema": "main",
                    "methods": ["GET"],
                    "primary_key": "id",
                    "fields": ["id", "email"],
                    "filters": ["email"],
                    "sortable": ["id"],
                }
            ],
        }
    )
    from fastapi import FastAPI

    app = FastAPI()
    mount_graphql(app, engine, spec)
    client = TestClient(app)
    res = client.post("/graphql", json={"query": "{ availableEndpoints }"})
    assert res.status_code == 200, res.text
    payload = res.json()
    assert not payload.get("errors"), payload
    assert "customers" in payload["data"]["availableEndpoints"]

    res2 = client.post(
        "/graphql",
        json={"query": '{ endpoint(name: "customers", limit: 5) }'},
    )
    assert res2.status_code == 200, res2.text
    body = res2.json()
    assert not body.get("errors"), body
    assert body["data"]["endpoint"][0]["email"] == "a@b.c"


def test_create_data_app_invokes_mount_graphql(monkeypatch: pytest.MonkeyPatch):
    """GA path: create_data_app always attempts mount_graphql (no experimental gate)."""
    called: dict[str, bool] = {}

    def _fake_mount(app, engine, spec):  # noqa: ANN001
        called["yes"] = True

    monkeypatch.setattr(
        "contractapi.application.graphql_facade.mount_graphql",
        _fake_mount,
    )
    pytest.importorskip("duckdb")
    pytest.importorskip("duckdb_engine")
    spec = parse_spec(
        {
            "database": {"url": "duckdb:///:memory:", "driver": "duckdb"},
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
                    "name": "demo",
                    "path": "/demo",
                    "sql": "SELECT 1 AS id",
                    "primary_key": "id",
                    "fields": ["id"],
                }
            ],
        }
    )
    create_data_app(spec)
    assert called.get("yes") is True


def test_mount_graphql_noop_without_table_gets():
    """SQL-only specs should not fail mount."""
    from unittest.mock import MagicMock

    spec = parse_spec(
        {
            "database": {"url": "postgresql://x/y"},
            "app": {
                "title": "S",
                "version": "0.5.0",
                "description": "t",
                "read_only": True,
                "auth": "none",
                "api_prefix": "",
            },
            "endpoints": [
                {
                    "name": "metrics",
                    "path": "/metrics",
                    "sql": "SELECT 1 AS id",
                    "primary_key": "id",
                    "fields": ["id"],
                }
            ],
        }
    )
    app = MagicMock()
    engine = MagicMock()
    mount_graphql(app, engine, spec)
    app.include_router.assert_not_called()
