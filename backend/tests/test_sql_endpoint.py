from fastapi.testclient import TestClient
from sqlalchemy import text

from contractapi.application.data_api_builder import create_data_app
from contractapi.domain.models.spec import parse_spec
from contractapi.infrastructure.db.engine import create_pg_engine


def _pg_or_skip():
    import pytest

    try:
        engine = create_pg_engine(
            "postgresql://postgres:postgres@localhost:5433/app", pooled=False
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine
    except Exception:
        pytest.skip("Postgres demo unavailable")


def test_sql_metrics_endpoint_and_csv():
    _pg_or_skip()
    spec = parse_spec(
        {
            "database": {"url": "postgresql://postgres:postgres@localhost:5433/app"},
            "app": {"read_only": True, "auth": "none", "api_prefix": "/v1"},
            "endpoints": [
                {
                    "name": "customer_metrics",
                    "path": "/analytics/customers",
                    "sql": (
                        "SELECT id, name, email, created_at "
                        "FROM customers WHERE deleted_at IS NULL"
                    ),
                    "fields": ["id", "name", "email", "created_at"],
                    "primary_key": "id",
                    "filters": ["name"],
                    "sortable": ["id", "name"],
                    "pagination": {"mode": "offset", "default_limit": 10, "max_limit": 50},
                    "csv_export": True,
                }
            ],
        }
    )
    client = TestClient(create_data_app(spec))
    res = client.get("/v1/analytics/customers", params={"limit": 2})
    assert res.status_code == 200, res.text
    body = res.json()
    assert "items" in body
    assert len(body["items"]) <= 2

    csv_res = client.get(
        "/v1/analytics/customers",
        params={"limit": 2, "format": "csv"},
    )
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers.get("content-type", "")
    assert "id,name,email,created_at" in csv_res.text.splitlines()[0]


def test_sql_rejects_writes_and_dangerous():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        parse_spec(
            {
                "database": {"url": "postgresql://x/y"},
                "app": {"read_only": False, "auth": "none"},
                "endpoints": [
                    {
                        "name": "bad",
                        "path": "/bad",
                        "sql": "DELETE FROM customers",
                        "fields": ["id"],
                    }
                ],
            }
        )
