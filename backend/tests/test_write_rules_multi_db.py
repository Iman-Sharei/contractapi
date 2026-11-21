# ruff: noqa: F811 — `db` is the shared pytest fixture imported from test_multi_database
"""Spec write rules on Postgres, MySQL and SQL Server: timestamps, defaults/fixed values,
all-or-nothing bulk, nested children, restore / reuse of soft-deleted rows, exact decimals,
time zones and schema changes under a running API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from test_multi_database import PEOPLE_EP, URLS, H, _client, _engine, _spec, db  # noqa: F401

from contractapi.application.schema_drift import check_database_changes
from contractapi.domain.models.spec import JwtConfig, parse_spec
from contractapi.infrastructure.security.jwt_tokens import issue_token

WRITE = {"methods": ["GET", "POST", "PATCH", "DELETE"]}
ORDERS_REL = {
    "name": "orders",
    "table": "mdb_orders",
    "local_key": "id",
    "foreign_key": "person_id",
    "fields": ["id", "total", "status"],
}


def _count(db: str, where: str) -> int:
    with _engine(db).connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM mdb_people WHERE {where}")).scalar_one()


def test_timestamps_defaults_and_fixed_values(db):
    ep = {
        **PEOPLE_EP,
        **WRITE,
        "fields": [*PEOPLE_EP["fields"], "updated_at"],
        "writable_fields": ["name", "email", "score", "tenant", "updated_at"],
        "timestamps": {"updated_at": "updated_at"},
        "defaults": {"score": 7},
        "fixed_values": {"tenant": "API"},
    }
    spec = _spec(db, [ep], read_only=False)
    spec["database"]["timezone"] = "UTC"
    from fastapi.testclient import TestClient

    from contractapi.application.data_api_builder import create_data_app

    c = TestClient(create_data_app(parse_spec(spec)))
    made = c.post("/people", json={"name": "Barbara", "email": "b@example.com"}, headers=H)
    assert made.status_code == 201, made.text
    row = made.json()
    assert row["score"] == 7 and row["tenant"] == "API"  # default + fixed value
    stamped = datetime.fromisoformat(row["updated_at"])
    assert stamped.utcoffset() == timedelta(0)  # naive column, reported in the database time zone
    assert abs(datetime.now(timezone.utc) - stamped) < timedelta(minutes=2)

    # The API owns these columns: a client value is refused, not silently dropped.
    for field in ("tenant", "updated_at"):
        refused = c.post("/people", json={"name": "X", "email": "x@example.com", field: "B"}, headers=H)
        assert refused.status_code == 422, (field, refused.text)

    upd = c.patch(f"/people/{row['id']}", json={"score": 1}, headers=H)
    assert upd.status_code == 200, upd.text
    assert upd.json()["tenant"] == "API"
    assert datetime.fromisoformat(upd.json()["updated_at"]) >= stamped


def test_bulk_all_or_nothing(db):
    ep = {**PEOPLE_EP, **WRITE, "writable_fields": ["name", "email"], "bulk_atomic": True}
    c = _client(db, [ep], read_only=False)
    before = _count(db, "1=1")
    dup = c.post(
        "/people/bulk",
        json={"items": [{"name": "K", "email": "k@example.com"}, {"name": "D", "email": "ada@example.com"}]},
        headers=H,
    )
    assert dup.status_code == 409, dup.text
    assert dup.json()["errors"][0]["index"] == 1 and "Nothing was saved" in dup.json()["errors"][0]["detail"]
    invalid = c.post("/people/bulk", json={"items": [{"name": "K", "email": "k@example.com"}, {"nope": 1}]}, headers=H)
    assert invalid.status_code == 422 and invalid.json()["errors"][0]["index"] == 1
    assert _count(db, "1=1") == before  # neither request stored anything
    ok = c.post("/people/bulk", json={"items": [{"name": "K", "email": "k@example.com"}]}, headers=H)
    assert ok.status_code == 201 and _count(db, "1=1") == before + 1


def test_nested_children_are_created_with_the_parent(db):
    ep = {
        **PEOPLE_EP,
        **WRITE,
        "writable_fields": ["name", "email"],
        "relations": [ORDERS_REL],
        "nested_writes": ["orders"],
    }
    c = _client(db, [ep], read_only=False, decimals="string")
    body = {
        "name": "Barbara",
        "email": "b@example.com",
        "orders": [{"total": "10.50", "status": "paid"}, {"total": 3, "status": "new"}],
    }
    made = c.post("/people", json=body, headers=H)
    assert made.status_code == 201, made.text
    kids = made.json()["orders"]
    assert [k["total"] for k in kids] == ["10.50", "3.00"] and all(isinstance(k["id"], int) for k in kids)
    got = c.get(f"/people/{made.json()['id']}", headers=H).json()
    assert sorted(o["status"] for o in got["orders"]) == ["new", "paid"]

    # A child may not choose its parent; a failing child rolls the parent back.
    steal = c.post("/people", json={**body, "email": "s@example.com", "orders": [{"total": 1, "status": "x", "person_id": 1}]}, headers=H)
    assert steal.status_code == 422, steal.text
    broken = c.post("/people", json={**body, "email": "r@example.com", "orders": [{"total": 1}]}, headers=H)
    assert broken.status_code == 422, broken.text  # status is NOT NULL: say what is missing
    assert "required value is missing" in broken.json()["detail"]
    assert _count(db, "email IN ('s@example.com', 'r@example.com')") == 0
    too_many = c.post("/people", json={**body, "orders": [{"total": 1, "status": "x"}] * 101}, headers=H)
    assert too_many.status_code == 422


def test_restore_and_reuse_of_soft_deleted_rows(db):
    ep = {
        **PEOPLE_EP,
        **WRITE,
        "writable_fields": ["name", "email"],
        "soft_delete": {"column": "deleted_at", "restore": True, "reuse_deleted": True},
    }
    c = _client(db, [ep], read_only=False)
    made = c.post("/people", json={"name": "Barbara", "email": "b@example.com"}, headers=H).json()
    pid = made["id"]
    assert c.delete(f"/people/{pid}", headers=H).status_code == 204
    assert c.get(f"/people/{pid}", headers=H).status_code == 404
    back = c.post(f"/people/{pid}/restore", headers=H)
    assert back.status_code == 200 and back.json()["email"] == "b@example.com", back.text
    assert c.post(f"/people/{pid}/restore", headers=H).status_code == 200  # already live: no-op
    assert c.post("/people/999999/restore", headers=H).status_code == 404
    assert c.post(f"/people/{pid}/restore").status_code == 401

    assert c.delete(f"/people/{pid}", headers=H).status_code == 204
    again = c.post("/people", json={"name": "Barbara L.", "email": "b@example.com"}, headers=H)
    assert again.status_code == 201, again.text  # the deleted row is reused, not a 409
    assert again.json()["id"] == pid and again.json()["name"] == "Barbara L."
    assert _count(db, "email = 'b@example.com'") == 1
    live = c.post("/people", json={"name": "Twin", "email": "b@example.com"}, headers=H)
    assert live.status_code == 409  # a live row still blocks the value


def test_reuse_deleted_never_takes_another_tenants_row(db):
    ep = {
        **PEOPLE_EP,
        **WRITE,
        "writable_fields": ["name", "email", "tenant"],
        "row_level": {"column": "tenant", "claim": "tenant"},
        "soft_delete": {"column": "deleted_at", "restore": True, "reuse_deleted": True},
    }
    c = _client(db, [ep], auth="jwt", read_only=False)

    def as_tenant(t: str) -> dict:
        return {"Authorization": f"Bearer {issue_token(subject=t, roles=['x'], jwt_cfg=JwtConfig(), extra={'tenant': t})}"}

    grace = next(i for i in c.get("/people", headers=as_tenant("B")).json()["items"] if i["name"] == "Grace Hopper")
    assert c.delete(f"/people/{grace['id']}", headers=as_tenant("B")).status_code == 204
    assert c.post(f"/people/{grace['id']}/restore", headers=as_tenant("A")).status_code == 404
    taken = c.post("/people", json={"name": "Mallory", "email": "grace@example.com"}, headers=as_tenant("A"))
    assert taken.status_code == 409  # not revived into tenant A
    assert c.post(f"/people/{grace['id']}/restore", headers=as_tenant("B")).status_code == 200


def test_decimals_as_exact_text_in_rest_and_graphql(db):
    ep = {
        "name": "orders",
        "path": "/orders",
        "table": "mdb_orders",
        "fields": ["id", "person_id", "total", "status"],
        "methods": ["GET", "POST"],
        "writable_fields": ["person_id", "total", "status"],
    }
    c = _client(db, [ep], read_only=False, decimals="string")
    totals = sorted(i["total"] for i in c.get("/orders", headers=H).json()["items"])
    assert totals == ["120.50", "40.00", "999.99"]
    pid = c.get("/orders", headers=H).json()["items"][0]["person_id"]
    made = c.post("/orders", json={"person_id": pid, "total": "1234567890.12", "status": "new"}, headers=H)
    assert made.status_code == 201 and made.json()["total"] == "1234567890.12", made.text
    pytest.importorskip("strawberry")
    gql = c.post("/graphql", json={"query": '{ endpoint(name: "orders", limit: 10) }'}, headers=H).json()
    assert "1234567890.12" in {o["total"] for o in gql["data"]["endpoint"]}  # same text as REST


def test_schema_change_under_a_running_api_is_explained(db):
    spec = parse_spec(_spec(db, [PEOPLE_EP]))
    from fastapi.testclient import TestClient

    from contractapi.application.data_api_builder import create_data_app

    c = TestClient(create_data_app(spec))
    rename = (
        "EXEC sp_rename 'mdb_people.score', 'points', 'COLUMN'"
        if db == "sqlserver"
        else "ALTER TABLE mdb_people RENAME COLUMN score TO points"
    )
    with _engine(db).begin() as conn:
        conn.execute(text(rename))
    res = c.get("/people", headers=H)
    assert res.status_code == 409, res.text
    body = res.json()
    assert body["type"].endswith("/schema-changed") and "Check database changes" in body["detail"]
    assert "points" not in body["detail"] and "mdb_people" not in body["detail"]  # no internals

    report = check_database_changes(spec)
    people = report["endpoints"][0]
    assert report["ok"] is False and people["status"] == "changed"
    assert people["missing"] == ["score"] and "points" in people["new_columns"]
    assert "password_hash" not in people["new_columns"]  # sensitive columns are not suggested
    assert URLS[db]  # keep import used for clarity of which database ran


def test_schema_change_in_a_related_table_is_explained_too(db):
    c = _client(db, [{**PEOPLE_EP, "relations": [{**ORDERS_REL, "fields": ["id", "total", "status"]}]}])
    pid = c.get("/people?limit=1", headers=H).json()["items"][0]["id"]
    rename = (
        "EXEC sp_rename 'mdb_orders.status', 'state', 'COLUMN'"
        if db == "sqlserver"
        else "ALTER TABLE mdb_orders RENAME COLUMN status TO state"
    )
    with _engine(db).begin() as conn:
        conn.execute(text(rename))
    for url in (f"/people/{pid}", "/people?limit=5&q=zz"):
        res = c.get(url, headers=H)
        if res.status_code != 200:  # an empty page loads no relations
            assert res.status_code == 409 and res.json()["type"].endswith("/schema-changed"), res.text
    assert c.get(f"/people/{pid}", headers=H).status_code == 409


def test_embedded_rows_use_the_same_value_format(db):
    spec = _spec(db, [{**PEOPLE_EP, "relations": [ORDERS_REL]}], decimals="string")
    spec["database"]["timezone"] = "UTC"
    from fastapi.testclient import TestClient

    from contractapi.application.data_api_builder import create_data_app

    c = TestClient(create_data_app(parse_spec(spec)))
    ada = next(i for i in c.get("/people?limit=10", headers=H).json()["items"] if i["name"] == "Ada Lovelace")
    assert sorted(o["total"] for o in ada["orders"]) == ["120.50", "40.00"]


def test_graphql_writes_follow_the_same_rules(db):
    pytest.importorskip("strawberry")
    ep = {**PEOPLE_EP, **WRITE, "writable_fields": ["name", "email", "tenant"],
          "fixed_values": {"tenant": "API"}, "defaults": {"score": 5}}
    c = _client(db, [ep], read_only=False)

    def gql(q: str) -> dict:
        return c.post("/graphql", json={"query": q}, headers=H).json()

    made = gql('mutation { createItem(endpoint: "people", data: {name: "G", email: "g@example.com"}) }')
    assert made["data"]["createItem"]["tenant"] == "API" and made["data"]["createItem"]["score"] == 5
    refused = gql('mutation { createItem(endpoint: "people", data: {name: "H", email: "h@example.com", tenant: "B"}) }')
    assert refused["data"] is None and "cannot be written" in refused["errors"][0]["message"]
