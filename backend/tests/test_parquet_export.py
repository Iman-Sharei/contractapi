import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from contractapi.application.data_api_builder import create_data_app
from contractapi.domain.models.spec import parse_spec


pyarrow = pytest.importorskip("pyarrow")


def _pg_or_skip():
    try:
        from contractapi.infrastructure.db.engine import create_pg_engine

        engine = create_pg_engine(
            "postgresql://postgres:postgres@localhost:5433/app", pooled=False
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine
    except Exception:
        pytest.skip("Postgres demo unavailable")


def test_parquet_export_list():
    _pg_or_skip()
    spec = parse_spec(
        {
            "database": {"url": "postgresql://postgres:postgres@localhost:5433/app"},
            "app": {"read_only": True, "auth": "none", "api_prefix": "/v1"},
            "endpoints": [
                {
                    "name": "customers",
                    "path": "/customers",
                    "table": "customers",
                    "fields": ["id", "name", "email"],
                    "primary_key": "id",
                    "pagination": {"mode": "offset", "default_limit": 5, "max_limit": 20},
                    "parquet_export": True,
                }
            ],
        }
    )
    client = TestClient(create_data_app(spec))
    res = client.get("/v1/customers", params={"limit": 2, "format": "parquet"})
    assert res.status_code == 200, res.text
    assert "parquet" in res.headers.get("content-type", "")
    assert len(res.content) > 0

    import io

    import pyarrow.parquet as pq

    table = pq.read_table(io.BytesIO(res.content))
    assert set(table.column_names) == {"id", "name", "email"}
    assert table.num_rows <= 2
