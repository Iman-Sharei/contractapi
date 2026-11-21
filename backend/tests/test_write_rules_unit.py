"""Spec checks for write rules, warehouse nested columns, DB error mapping, Studio drift route.
No database needed (DuckDB in memory where a real engine helps)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Column, Integer, MetaData, String, Table
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.types import UserDefinedType

from contractapi.application.data_api.common import OUTPUT_FORMAT, OutputFormat, _serialize
from contractapi.application.warehouse_types import NestedJson, prepare_nested_columns
from contractapi.core.config import get_settings
from contractapi.core.errors import AppError
from contractapi.domain.models.spec import DatabaseDriver, EndpointSpec, parse_spec
from contractapi.infrastructure.db.errors import db_error
from contractapi.interfaces.http.app_factory import create_studio_app

BASE = {"name": "people", "path": "/people", "table": "people", "fields": ["id", "name", "status"]}
REL = {"name": "orders", "table": "orders", "local_key": "id", "foreign_key": "person_id",
       "fields": ["id", "total"]}


def _ep(**kw) -> EndpointSpec:
    return EndpointSpec.model_validate({**BASE, **kw})


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ({"nested_writes": ["orders"], "methods": ["GET", "POST"]}, "not one of its relations"),
        ({"nested_writes": ["orders"], "methods": ["GET"], "relations": [REL]}, "need POST"),
        ({"nested_writes": ["orders"], "methods": ["GET", "POST"], "async_writes": True,
          "relations": [REL]}, "async_writes"),
        ({"nested_writes": ["orders"], "methods": ["GET", "POST"],
          "relations": [{**REL, "type": "many_to_one"}]}, "one_to_many"),
        ({"fixed_values": {"id": 1}}, "primary key"),
        ({"fixed_values": {"status": {"a": 1}}}, "text, a number"),
        ({"defaults": {"bad name": 1}}, "not a column name"),
        ({"soft_delete": {"restore": True}, "methods": ["GET", "PATCH"]}, "allow DELETE"),
        ({"row_level": {"column": "status"}, "fixed_values": {"status": "x"}}, "caller's token"),
    ],
)
def test_write_rules_are_checked_with_actionable_messages(extra, message):
    with pytest.raises(ValidationError, match=message):
        _ep(**extra)


def test_api_managed_columns_are_not_writable_by_clients():
    ep = _ep(
        methods=["GET", "POST", "PATCH"],
        fields=["id", "name", "status", "updated_at"],
        fixed_values={"status": "new"},
        timestamps={"updated_at": "updated_at"},
    )
    assert ep.writable_fields == ["name"]


def test_timezone_and_decimals_options():
    spec = {"database": {"url": "mysql://u@h/db", "timezone": "Asia/Tehran"},
            "app": {"decimals": "string"}, "endpoints": [BASE]}
    parsed = parse_spec(spec)
    assert parsed.database.timezone == "Asia/Tehran" and parsed.app.decimals == "string"
    with pytest.raises(ValidationError, match="not a known time zone"):
        parse_spec({**spec, "database": {"url": "mysql://u@h/db", "timezone": "Mars/Olympus"}})
    with pytest.raises(ValidationError):
        parse_spec({**spec, "app": {"decimals": "float"}})


def test_serializer_follows_the_api_output_format():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    naive = datetime(2026, 1, 2, 3, 4, 5)
    assert _serialize(Decimal("12.50")) == 12.5 and _serialize(naive) == "2026-01-02T03:04:05"
    token = OUTPUT_FORMAT.set(OutputFormat(decimals="string", tz=ZoneInfo("UTC")))
    try:
        assert _serialize(Decimal("1E+2")) == "100"  # never scientific notation
        assert _serialize(Decimal("0.10")) == "0.10"
        assert _serialize(naive) == "2026-01-02T03:04:05+00:00"
    finally:
        OUTPUT_FORMAT.reset(token)


class VARIANT(UserDefinedType):  # stands in for snowflake.sqlalchemy.VARIANT
    cache_ok = True

    def get_col_spec(self, **kw):
        return "VARIANT"


def _wh_table() -> Table:
    return Table("events", MetaData(), Column("id", Integer, primary_key=True),
                 Column("name", String), Column("payload", VARIANT()))


def test_warehouse_nested_columns_become_json_and_cannot_be_filtered():
    ep = _ep(table="events", fields=["id", "name", "payload"])
    table = _wh_table()
    assert prepare_nested_columns(table, ep, DatabaseDriver.POSTGRES) == []  # only warehouses
    assert prepare_nested_columns(table, ep, DatabaseDriver.SNOWFLAKE) == ["payload"]
    parse = NestedJson().process_result_value
    assert parse('{"a": [1, 2]}', None) == {"a": [1, 2]}
    assert parse({"already": "dict"}, None) == {"already": "dict"}  # BigQuery STRUCT
    assert parse("not json", None) == "not json"

    for extra in ({"filters": ["payload"]}, {"sortable": ["payload"]}):
        bad = _ep(table="events", fields=["id", "name", "payload"], **extra)
        with pytest.raises(AppError, match="nested data") as err:
            prepare_nested_columns(_wh_table(), bad, DatabaseDriver.BIGQUERY)
        assert err.value.status == 400


@pytest.mark.parametrize(
    "message",
    [
        'column "score" does not exist',  # Postgres
        "(1054, \"Unknown column 'score' in 'field list'\")",  # MySQL
        "(1146, \"Table 'app.people' doesn't exist\")",
        "(207, b\"Invalid column name 'score'.DB-Lib error message 20018\")",  # SQL Server
        "Binder Error: Referenced column \"score\" not found",  # DuckDB
        "000904 (42000): SQL compilation error: invalid identifier 'SCORE'",  # Snowflake
        "Unrecognized name: score at [1:8]",  # BigQuery
    ],
)
def test_schema_changes_map_to_one_clear_problem(message):
    err = db_error(ProgrammingError("SELECT …", {}, Exception(message)))
    assert err.status == 409 and err.type.endswith("/schema-changed")
    assert "score" not in err.detail and "SELECT" not in err.detail


@pytest.mark.parametrize(
    ("exc_type", "message"),
    [
        (IntegrityError, 'null value in column "status" violates not-null constraint'),
        (OperationalError, "(1364, \"Field 'status' doesn't have a default value\")"),
        (IntegrityError, "(515, b\"Cannot insert the value NULL into column 'status'\")"),
    ],
)
def test_missing_required_value_is_422_not_conflict_or_500(exc_type, message):
    from contractapi.application.data_api.write_support import conflict_error

    exc = exc_type("INSERT …", {}, Exception(message))
    for err in (db_error(exc), conflict_error(exc)):
        assert err.status == 422 and "required value is missing" in err.detail


def test_studio_database_changes_route_needs_the_key_and_a_saved_api(monkeypatch, tmp_path):
    monkeypatch.setenv("SPECS_DIR", str(tmp_path))
    get_settings.cache_clear()
    client = TestClient(create_studio_app())
    assert client.get("/studio/specs/nope/database-changes").status_code == 401
    key = {"X-API-Key": get_settings().studio_api_key}
    missing = client.get("/studio/specs/nope/database-changes", headers=key)
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/problem+json")
    get_settings.cache_clear()


def test_write_rules_example_round_trips_through_yaml():
    from pathlib import Path

    import yaml

    from contractapi.domain.models.spec import dump_spec, load_spec

    spec = load_spec(Path(__file__).parent.parent / "examples" / "write_rules.yaml")
    again = parse_spec(yaml.safe_load(dump_spec(spec)))
    assert again.model_dump() == spec.model_dump()
    customers = again.endpoints[0]
    assert customers.nested_writes == ["orders"] and customers.soft_delete.reuse_deleted
    assert again.app.decimals == "string" and again.database.timezone == "UTC"


def test_an_api_that_cannot_start_answers_503_and_is_retried(monkeypatch):
    from contractapi.interfaces.http import app_factory

    spec = parse_spec({"database": {"url": "postgresql://u:p@127.0.0.1:1/none"}, "endpoints": [BASE]})
    app, failed_at = app_factory._build_api("broken", spec)
    assert failed_at is not None
    res = TestClient(app).get("/people")
    assert res.status_code == 503 and res.headers["retry-after"] == str(app_factory.RETRY_SECONDS)
    body = res.json()
    assert body["type"].endswith("/api-unavailable") and "Check database changes" in body["detail"]
    assert "127.0.0.1" not in body["detail"]  # no connection details to callers
    assert not app_factory._due(failed_at)
    monkeypatch.setattr(app_factory.time, "monotonic", lambda: failed_at + app_factory.RETRY_SECONDS)
    assert app_factory._due(failed_at)


def test_saving_an_invalid_api_file_says_why_instead_of_500(monkeypatch, tmp_path):
    monkeypatch.setenv("SPECS_DIR", str(tmp_path))
    get_settings.cache_clear()
    client = TestClient(create_studio_app())
    key = {"X-API-Key": get_settings().studio_api_key}
    bad = {"database": {"url": "postgresql://u@h/db", "timezone": "Mars/Olympus"}, "endpoints": [BASE]}
    res = client.post("/studio/specs", json={"name": "tz_test", "spec": bad}, headers=key)
    assert res.status_code == 400, res.text
    assert res.json()["type"].endswith("/invalid-spec") and "not a known time zone" in res.json()["detail"]
    get_settings.cache_clear()
