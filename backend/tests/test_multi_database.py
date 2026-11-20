"""The same API behaviour on Postgres, MySQL and SQL Server.

Each database is skipped when it is not reachable. Start them with:
    docker compose up -d db
    docker compose --profile mysql --profile sqlserver up -d mysql sqlserver
URLs can be overridden with MDB_POSTGRES_URL / MDB_MYSQL_URL / MDB_SQLSERVER_URL.
"""

from __future__ import annotations

import os
from functools import cache

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    func,
    text,
)

from contractapi.application.data_api_builder import create_data_app
from contractapi.application.studio_service import introspect, validate_spec_payload
from contractapi.core.config import get_settings
from contractapi.domain.models.spec import DatabaseConfig, JwtConfig, parse_spec
from contractapi.infrastructure.cache_store import response_cache
from contractapi.infrastructure.db.engine import create_engine_for_config
from contractapi.infrastructure.security.jwt_tokens import issue_token

URLS = {
    "postgres": os.getenv("MDB_POSTGRES_URL", "postgresql://postgres:postgres@localhost:5433/app"),
    "mysql": os.getenv("MDB_MYSQL_URL", "mysql://demo:demo@localhost:3307/app"),
    "sqlserver": os.getenv("MDB_SQLSERVER_URL", "mssql://sa:Demo_pass_2024!@localhost:1434/master"),
}
KEY = "mdb-key"

meta = MetaData()
people = Table(
    "mdb_people",
    meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False),
    Column("email", String(100), nullable=False, unique=True),
    Column("password_hash", String(100), nullable=False, server_default="x"),
    Column("tenant", String(20)),
    Column("score", Integer, nullable=False, server_default="0"),
    Column("deleted_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
orders = Table(
    "mdb_orders",
    meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("person_id", Integer, ForeignKey("mdb_people.id"), nullable=False),
    Column("total", Numeric(12, 2), nullable=False),
    Column("status", String(20), nullable=False),
)

PEOPLE = [
    ("Ada Lovelace", "ada@example.com", "A", 3),
    ("Alan Turing", "alan@example.com", "A", 4),
    ("Grace Hopper", "grace@example.com", "B", 4),
    ("Edsger Dijkstra", "edsger@example.com", "B", 1),
]


def _engine(db: str):
    return create_engine_for_config(DatabaseConfig(url=URLS[db]), pooled=False)


@cache
def _reachable(db: str) -> bool:
    try:
        with _engine(db).connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.fixture(params=["postgres", "mysql", "sqlserver"])
def db(request, monkeypatch, tmp_path):
    name = request.param
    if not _reachable(name):
        if os.getenv("MDB_REQUIRE_ALL"):  # CI: a missing database is a failure, not a skip
            pytest.fail(f"{name} not reachable")
        pytest.skip(f"{name} not reachable")
    monkeypatch.setenv("SPECS_DIR", str(tmp_path / "specs"))
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("DATA_API_KEYS", KEY)
    monkeypatch.setenv("JWT_SECRET", "multi-database-test-secret-0123456789abcdef")
    get_settings.cache_clear()
    response_cache.clear()
    engine = _engine(name)
    meta.drop_all(engine)
    meta.create_all(engine)
    with engine.begin() as conn:
        ids = []
        for n, e, t, s in PEOPLE:
            res = conn.execute(people.insert().values(name=n, email=e, tenant=t, score=s))
            ids.append(res.inserted_primary_key[0])
        conn.execute(
            orders.insert(),
            [
                {"person_id": ids[0], "total": 120.50, "status": "paid"},
                {"person_id": ids[0], "total": 40.00, "status": "pending"},
                {"person_id": ids[1], "total": 999.99, "status": "paid"},
            ],
        )
    yield name
    meta.drop_all(engine)
    get_settings.cache_clear()


def _spec(db: str, endpoints: list[dict], **app) -> dict:
    return {
        "database": {"url": URLS[db]},
        "app": {"title": "MDB", "api_prefix": "", "auth": "api_key", "read_only": True, **app},
        "endpoints": endpoints,
    }


PEOPLE_EP = {
    "name": "people",
    "path": "/people",
    "table": "mdb_people",
    "fields": ["id", "name", "email", "tenant", "score", "created_at"],
    "filters": ["name", "email", "score", "tenant", "id"],
    "sortable": ["id", "name", "score"],
}


def _client(db: str, endpoints: list[dict], **app) -> TestClient:
    return TestClient(create_data_app(parse_spec(_spec(db, endpoints, **app))))


H = {"X-API-Key": KEY}


def test_introspect_finds_tables_keys_and_private_columns(db):
    tables = {t["name"]: t for t in introspect(URLS[db])}
    p = tables["mdb_people"]
    assert p["primary_keys"] == ["id"]
    assert "password_hash" in p["sensitive_columns"]
    assert {"column": "person_id", "ref_table": "mdb_people", "ref_column": "id"} in tables[
        "mdb_orders"
    ]["foreign_keys"]
    # The schema Studio stores must load again (database name on MySQL, dbo on SQL Server).
    expected = {"postgres": "public", "mysql": "app", "sqlserver": "dbo"}[db]
    assert p["schema"] == expected


def test_validate_checks_columns_on_every_database(db):
    good = _spec(db, [{**PEOPLE_EP, "schema": "public"}])
    assert validate_spec_payload(good)["valid"] is True
    bad = _spec(db, [{**PEOPLE_EP, "fields": ["id", "nope"], "filters": [], "sortable": ["id"]}])
    result = validate_spec_payload(bad)
    assert result["valid"] is False
    assert any("missing columns: nope" in e for e in result["errors"])


def test_list_paging_sort_and_filters(db):
    c = _client(db, [{**PEOPLE_EP, "pagination": {"mode": "offset", "default_limit": 2}}])
    assert c.get("/people").status_code == 401  # no key

    page = c.get("/people?limit=2&offset=2&sort=-score", headers=H).json()
    assert page["total"] == 4 and len(page["items"]) == 2
    assert [i["score"] for i in page["items"]] == [3, 1]
    assert "password_hash" not in page["items"][0]

    def names(q: str) -> list[str]:
        r = c.get(f"/people?{q}", headers=H)
        assert r.status_code == 200, r.text
        return sorted(i["name"] for i in r.json()["items"])

    assert names("name__contains=LOVE") == ["Ada Lovelace"]  # case-insensitive everywhere
    assert names("name__startswith=al") == ["Alan Turing"]
    assert names("score__gte=4") == ["Alan Turing", "Grace Hopper"]
    assert names("tenant__in=B") == ["Edsger Dijkstra", "Grace Hopper"]
    assert names("email__contains=50%25") == []  # % is a literal, not a wildcard
    assert names("q=hopper") == ["Grace Hopper"]
    assert c.get("/people?password_hash=x", headers=H).status_code == 400
    assert c.get("/people?sort=email", headers=H).status_code == 400
    assert c.get("/people?score=abc", headers=H).status_code == 400


def test_cursor_paging_and_relations(db):
    ep = {
        **PEOPLE_EP,
        "pagination": {"mode": "cursor", "default_limit": 3},
        "relations": [
            {
                "name": "orders",
                "table": "mdb_orders",
                "type": "one_to_many",
                "local_key": "id",
                "foreign_key": "person_id",
                "fields": ["id", "person_id", "total", "status"],
            }
        ],
    }
    c = _client(db, [ep])
    first = c.get("/people", headers=H)
    body = first.json()
    assert len(body["items"]) == 3 and body["next_cursor"]
    assert "rel=\"next\"" in first.headers.get("link", "")
    ada = body["items"][0]
    assert sorted(float(o["total"]) for o in ada["orders"]) == [40.0, 120.5]
    unsorted = c.get("/people?sort=-score", headers=H)  # next-page links can't sort by score
    assert unsorted.status_code == 400 and "page numbers" in unsorted.json()["detail"]
    rest = c.get(f"/people?cursor={body['next_cursor']}", headers=H).json()
    assert [i["name"] for i in rest["items"]] == ["Edsger Dijkstra"] and rest["next_cursor"] is None
    assert c.get(f"/people/{ada['id']}", headers=H).json()["email"] == "ada@example.com"
    assert c.get("/people/999999", headers=H).status_code == 404


def test_create_update_delete_and_soft_delete(db):
    ep = {
        **PEOPLE_EP,
        "methods": ["GET", "POST", "PATCH", "DELETE"],
        "writable_fields": ["name", "email", "score"],
        "soft_delete": {"column": "deleted_at"},
    }
    c = _client(db, [ep], read_only=False)
    created = c.post("/people", json={"name": "Barbara Liskov", "email": "b@example.com"}, headers=H)
    assert created.status_code == 201, created.text
    row = created.json()
    assert isinstance(row["id"], int) and row["score"] == 0 and row["created_at"]  # DB defaults
    dup = c.post("/people", json={"name": "X", "email": "b@example.com"}, headers=H)
    assert dup.status_code == 409
    bad = c.post("/people", json={"name": "X", "email": "y@example.com", "tenant": "Z"}, headers=H)
    assert bad.status_code == 422  # tenant is not writable

    bulk = c.post(
        "/people/bulk",
        json={"items": [{"name": "K", "email": "k@example.com"}, {"name": "D", "email": "b@example.com"}]},
        headers=H,
    )
    assert bulk.status_code == 207, bulk.text  # one stored, one rejected (duplicate email)
    assert [i["email"] for i in bulk.json()["items"]] == ["k@example.com"]
    assert bulk.json()["errors"][0]["status"] == 409

    upd = c.patch(f"/people/{row['id']}", json={"score": 9}, headers=H)
    assert upd.status_code == 200 and upd.json()["score"] == 9
    same = c.patch(f"/people/{row['id']}", json={"score": 9}, headers=H)  # no actual change
    assert same.status_code == 200, same.text
    assert c.patch("/people/999999", json={"score": 1}, headers=H).status_code == 404

    assert c.delete(f"/people/{row['id']}", headers=H).status_code == 204

    hard = _client(db, [{**ep, "soft_delete": None}], read_only=False)
    ada = next(i for i in hard.get("/people?limit=50", headers=H).json()["items"] if i["name"] == "Ada Lovelace")
    in_use = hard.delete(f"/people/{ada['id']}", headers=H)  # Ada still has orders
    assert in_use.status_code == 409 and "refer to this one" in in_use.json()["detail"]
    assert c.get(f"/people/{row['id']}", headers=H).status_code == 404
    listed = [i["email"] for i in c.get("/people?limit=50", headers=H).json()["items"]]
    assert "b@example.com" not in listed
    with _engine(db).connect() as conn:  # soft delete: the row is still there
        assert conn.execute(text("SELECT COUNT(*) FROM mdb_people WHERE email = 'b@example.com'")).scalar_one() == 1


def test_row_level_forces_and_filters_the_tenant(db):
    ep = {
        **PEOPLE_EP,
        "methods": ["GET", "POST"],
        "writable_fields": ["name", "email", "tenant"],
        "row_level": {"column": "tenant", "claim": "tenant"},
    }
    c = _client(db, [ep], auth="jwt", read_only=False)
    tok = issue_token(subject="u", roles=["x"], jwt_cfg=JwtConfig(), extra={"tenant": "B"})
    hb = {"Authorization": f"Bearer {tok}"}
    assert c.get("/people").status_code == 401
    assert sorted(i["tenant"] for i in c.get("/people", headers=hb).json()["items"]) == ["B", "B"]
    other = c.post("/people", json={"name": "Z", "email": "z@example.com", "tenant": "A"}, headers=hb)
    assert other.status_code == 403  # cannot write into another tenant
    made = c.post("/people", json={"name": "Z", "email": "z@example.com"}, headers=hb)
    assert made.status_code == 201, made.text
    assert made.json()["tenant"] == "B"  # filled from the token


def test_custom_sql_endpoint_params_paging_and_detail(db):
    ep = {
        "name": "spend",
        "path": "/spend",
        "sql": (
            "SELECT p.id, p.name, COUNT(o.id) AS order_count, COALESCE(SUM(o.total), 0) AS spent "
            "FROM mdb_people p LEFT JOIN mdb_orders o ON o.person_id = p.id "
            "GROUP BY p.id, p.name HAVING COALESCE(SUM(o.total), 0) >= :min_spent"
        ),
        "sql_params": [{"name": "min_spent", "type": "float", "default": 0}],
        "fields": ["id", "name", "order_count", "spent"],
        "filters": ["name"],
        "filter_operators": ["eq", "contains"],
        "sortable": ["id", "spent"],
        "pagination": {"mode": "offset", "default_limit": 2},
    }
    c = _client(db, [ep])
    page = c.get("/spend?min_spent=100&sort=-spent", headers=H)
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["total"] == 2 and [i["name"] for i in body["items"]] == ["Alan Turing", "Ada Lovelace"]
    assert c.get("/spend?offset=2&limit=2", headers=H).json()["items"][0]["name"]
    assert [i["name"] for i in c.get("/spend?name__contains=GRACE", headers=H).json()["items"]] == [
        "Grace Hopper"
    ]
    one = c.get(f"/spend/{body['items'][0]['id']}", headers=H)
    assert one.status_code == 200 and one.json()["name"] == "Alan Turing"
    assert c.get("/spend?min_spent=abc", headers=H).status_code == 422


def test_aggregate_endpoint_and_avg_keeps_decimals(db):
    ep = {
        "name": "scores",
        "path": "/scores",
        "aggregate": {
            "table": "mdb_people",
            "group_by": ["tenant"],
            "metrics": [
                {"name": "people", "op": "count"},
                {"name": "avg_score", "op": "avg", "field": "score"},
            ],
            "where": [{"field": "score", "op": "gt", "value": 0}],
        },
        "pagination": {"mode": "offset"},
    }
    c = _client(db, [ep])
    r = c.get("/scores?sort=tenant", headers=H)
    assert r.status_code == 200, r.text
    rows = {i["tenant"]: i for i in r.json()["items"]}
    assert rows["A"]["people"] == 2 and float(rows["A"]["avg_score"]) == 3.5
    assert float(rows["B"]["avg_score"]) == 2.5


def test_graphql_returns_the_same_values_as_rest(db):
    pytest.importorskip("strawberry")
    c = _client(db, [PEOPLE_EP, {"name": "orders", "path": "/orders", "table": "mdb_orders", "fields": ["id", "total", "status"]}])
    rest = c.get("/people?limit=1", headers=H).json()["items"][0]
    gql = c.post("/graphql", json={"query": '{ endpoint(name: "people", limit: 1) }'}, headers=H).json()
    assert gql["data"]["endpoint"][0] == rest  # same ISO dates, same numbers
    rest_order = c.get("/orders?limit=1", headers=H).json()["items"][0]
    gql_order = c.post("/graphql", json={"query": '{ endpoint(name: "orders", limit: 1) }'}, headers=H).json()
    assert gql_order["data"]["endpoint"][0] == rest_order  # decimals as numbers in both


def test_connection_errors_are_readable_for_every_driver():
    from contractapi.infrastructure.db.errors import safe_db_message

    mssql = Exception(
        20009,
        b"DB-Lib error message 20009, severity 9:\nUnable to connect: TDS server is unavailable "
        b"or does not exist (sqlserver)\nNet-Lib error during Connection refused (111)\n",
    )
    assert safe_db_message(mssql) == (
        "Unable to connect: TDS server is unavailable or does not exist (sqlserver)"
    )
    wrapped = Exception((20009, b"DB-Lib error message 20009, severity 9:\nUnable to connect: x (h)\n"))
    assert safe_db_message(wrapped) == "Unable to connect: x (h)"  # pymssql's real shape
    mysql = Exception(2003, "Can't connect to MySQL server on 'mysql' ([Errno -2] Name or service not known)")
    assert safe_db_message(mysql).startswith("Can't connect to MySQL server on 'mysql'")
    pg = Exception('connection to server at "db" failed: password authentication failed for user "x"')
    assert "password authentication failed" in safe_db_message(pg)
    assert "s3cret" not in safe_db_message(Exception("bad url mysql://u:s3cret@h/db"))
