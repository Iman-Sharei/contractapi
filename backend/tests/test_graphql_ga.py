"""GraphQL facade — SQL reads + table mutations (GA when strawberry installed)."""

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


def _duck_engine():
    pytest.importorskip("duckdb")
    pytest.importorskip("duckdb_engine")
    url = "duckdb:///:memory:"
    engine = create_engine_for_config(
        DatabaseConfig(url=url, driver=DatabaseDriver.DUCKDB),
        pooled=False,
    )
    return url, engine


def test_graphql_table_and_sql_reads():
    if not graphql_available():
        pytest.skip("strawberry not installed")
    url, engine = _duck_engine()
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
                },
                {
                    "name": "metrics",
                    "path": "/metrics",
                    "sql": "SELECT 1 AS id, 'ok' AS status",
                    "primary_key": "id",
                    "fields": ["id", "status"],
                },
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
    assert set(payload["data"]["availableEndpoints"]) == {"customers", "metrics"}

    res2 = client.post(
        "/graphql",
        json={"query": '{ endpoint(name: "customers", limit: 5) }'},
    )
    assert res2.status_code == 200, res2.text
    body = res2.json()
    assert not body.get("errors"), body
    assert body["data"]["endpoint"][0]["email"] == "a@b.c"

    res3 = client.post(
        "/graphql",
        json={"query": '{ endpoint(name: "metrics", limit: 5) }'},
    )
    assert res3.status_code == 200, res3.text
    metrics = res3.json()
    assert not metrics.get("errors"), metrics
    assert metrics["data"]["endpoint"][0]["status"] == "ok"


def test_graphql_mutations_create_update_delete():
    if not graphql_available():
        pytest.skip("strawberry not installed")
    url, engine = _duck_engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY, name VARCHAR)"))

    spec = parse_spec(
        {
            "database": {"url": url, "driver": "duckdb"},
            "app": {
                "title": "GQL",
                "version": "0.5.0",
                "description": "t",
                "read_only": False,
                "auth": "none",
                "api_prefix": "",
            },
            "endpoints": [
                {
                    "name": "items",
                    "path": "/items",
                    "table": "items",
                    "schema": "main",
                    "methods": ["GET", "POST", "PATCH", "DELETE"],
                    "primary_key": "id",
                    "fields": ["id", "name"],
                    "writable_fields": ["id", "name"],
                    "filters": ["name"],
                    "sortable": ["id"],
                }
            ],
        }
    )
    from fastapi import FastAPI

    app = FastAPI()
    mount_graphql(app, engine, spec)
    client = TestClient(app)

    ops = client.post("/graphql", json={"query": "{ availableMutations }"})
    assert ops.status_code == 200, ops.text
    assert "create:items" in ops.json()["data"]["availableMutations"]

    created = client.post(
        "/graphql",
        json={
            "query": (
                'mutation { createItem(endpoint: "items", data: {id: 1, name: "alpha"}) }'
            )
        },
    )
    assert created.status_code == 200, created.text
    cbody = created.json()
    assert not cbody.get("errors"), cbody
    assert cbody["data"]["createItem"]["name"] == "alpha"

    updated = client.post(
        "/graphql",
        json={
            "query": (
                'mutation { updateItem(endpoint: "items", id: 1, data: {name: "beta"}) }'
            )
        },
    )
    assert updated.status_code == 200, updated.text
    ubody = updated.json()
    assert not ubody.get("errors"), ubody
    assert ubody["data"]["updateItem"]["name"] == "beta"

    deleted = client.post(
        "/graphql",
        json={"query": 'mutation { deleteItem(endpoint: "items", id: 1) }'},
    )
    assert deleted.status_code == 200, deleted.text
    dbody = deleted.json()
    assert not dbody.get("errors"), dbody
    assert dbody["data"]["deleteItem"]["deleted"] is True


def test_create_data_app_invokes_mount_graphql(monkeypatch: pytest.MonkeyPatch):
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


def test_mount_graphql_noop_without_get_or_writes():
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
                    "name": "dead",
                    "path": "/dead",
                    "table": "dead",
                    "methods": [],
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


def test_graphql_relations_and_rbac():
    if not graphql_available():
        pytest.skip("strawberry not installed")
    url, engine = _duck_engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE customers (id INTEGER, email VARCHAR)"))
        conn.execute(text("CREATE TABLE orders (id INTEGER, customer_id INTEGER, total DOUBLE)"))
        conn.execute(text("INSERT INTO customers VALUES (1, 'a@b.c'), (2, 'x@y.z')"))
        conn.execute(text("INSERT INTO orders VALUES (10, 1, 9.5), (11, 1, 1.0)"))

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
                "rbac": [
                    {
                        "role": "analyst",
                        "endpoints": {"customers": ["id", "email"]},
                    },
                    {
                        "role": "limited",
                        "endpoints": {"customers": ["id"]},
                    },
                ],
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
                    "relations": [
                        {
                            "name": "orders",
                            "table": "orders",
                            "schema": "main",
                            "type": "one_to_many",
                            "local_key": "id",
                            "foreign_key": "customer_id",
                            "fields": ["id", "customer_id", "total"],
                            "primary_key": "id",
                            "max_per_parent": 50,
                        }
                    ],
                }
            ],
        }
    )
    from fastapi import FastAPI

    app = FastAPI()
    mount_graphql(app, engine, spec)
    client = TestClient(app)

    full = client.post(
        "/graphql",
        json={
            "query": (
                '{ endpoint(name: "customers", limit: 5, includeRelations: true, '
                "roles: [\"analyst\"]) }"
            )
        },
    )
    assert full.status_code == 200, full.text
    fbody = full.json()
    assert not fbody.get("errors"), fbody
    row = next(r for r in fbody["data"]["endpoint"] if r["id"] == 1)
    assert row["email"] == "a@b.c"
    assert isinstance(row["orders"], list)
    assert len(row["orders"]) == 2

    limited = client.post(
        "/graphql",
        json={
            "query": (
                '{ endpoint(name: "customers", limit: 5, includeRelations: true, '
                "roles: [\"limited\"]) }"
            )
        },
    )
    assert limited.status_code == 200, limited.text
    lbody = limited.json()
    assert not lbody.get("errors"), lbody
    lrow = next(r for r in lbody["data"]["endpoint"] if r["id"] == 1)
    assert "email" not in lrow
    assert "orders" in lrow  # relation key retained when include_relations
