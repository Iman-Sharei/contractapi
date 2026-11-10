"""DuckDB driver is GA — no CONTRACTAPI_EXPERIMENTAL gate."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from contractapi.application.data_api_builder import create_data_app
from contractapi.core.config import Settings
from contractapi.domain.models.spec import DatabaseConfig, DatabaseDriver, parse_spec
from contractapi.infrastructure.db.engine import create_engine_for_config


def test_experimental_set_excludes_duckdb_and_parquet():
    s = Settings(experimental="all")
    assert "duckdb" not in s.experimental_set
    assert "parquet" not in s.experimental_set
    assert "graphql" in s.experimental_set


def test_create_engine_duckdb_without_experimental(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONTRACTAPI_EXPERIMENTAL", "")
    Settings.model_config  # noqa: B018 — touch model
    from contractapi.core.config import get_settings

    get_settings.cache_clear()
    try:
        duckdb = pytest.importorskip("duckdb")
        _ = duckdb
        pytest.importorskip("duckdb_engine")
        engine = create_engine_for_config(
            DatabaseConfig(url="duckdb:///:memory:", driver=DatabaseDriver.DUCKDB),
            pooled=False,
        )
        with engine.connect() as conn:
            row = conn.exec_driver_sql("SELECT 1 AS n").fetchone()
        assert row is not None
        assert int(row[0]) == 1
    finally:
        get_settings.cache_clear()


def test_duckdb_data_app_list():
    pytest.importorskip("duckdb")
    pytest.importorskip("duckdb_engine")
    spec = parse_spec(
        {
            "database": {"url": "duckdb:///:memory:", "driver": "duckdb"},
            "app": {
                "title": "Duck",
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
                    "sql": "SELECT 1 AS id, 'ok' AS status",
                    "primary_key": "id",
                    "fields": ["id", "status"],
                    "pagination": {
                        "mode": "offset",
                        "default_limit": 10,
                        "max_limit": 50,
                    },
                }
            ],
        }
    )
    app = create_data_app(spec)
    client = TestClient(app)
    res = client.get("/demo", params={"limit": 1})
    assert res.status_code == 200
    body = res.json()
    items = body.get("items") or body.get("data") or body
    if isinstance(items, dict):
        items = items.get("items", [items])
    assert isinstance(items, list)
    assert items[0]["id"] == 1
    assert items[0]["status"] == "ok"
