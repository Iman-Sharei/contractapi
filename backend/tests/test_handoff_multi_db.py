# ruff: noqa: F811 — `db` is the shared pytest fixture imported from test_multi_database
"""What another team receives and relies on, on Postgres, MySQL and SQL Server:
a complete OpenAPI, a working generated Python client, correct column types for writes,
and no way to change or page through rows by an id that is not unique."""

from __future__ import annotations

import types

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, String, Table
from test_multi_database import KEY, PEOPLE_EP, H, _client, _engine, _spec, db  # noqa: F401

from contractapi.application.client_exports import build_python_sdk, export_openapi
from contractapi.application.data_api_builder import create_data_app
from contractapi.domain.models.spec import parse_spec

WRITE = {"methods": ["GET", "POST", "PATCH", "DELETE"], "writable_fields": ["name", "email", "score"]}


def test_openapi_is_complete_enough_to_hand_over(db):
    doc = TestClient(create_data_app(parse_spec(_spec(db, [{**PEOPLE_EP, **WRITE}], read_only=False)))).get(
        "/openapi.json"
    ).json()
    # The key requirement is declared, so /docs has "Authorize" and clients send the header.
    assert doc["components"]["securitySchemes"]["ApiKey"] == {
        "type": "apiKey", "in": "header", "name": "X-API-Key",
        "description": "Create a key in Studio → Keys & settings",
    }
    assert doc["security"] == [{"ApiKey": []}]
    assert doc["paths"]["/health"]["get"]["security"] == []  # probes stay open

    listing = doc["paths"]["/people"]["get"]
    names = {p["name"] for p in listing["parameters"]}
    assert {"name", "name__contains", "score__gte", "score__in", "q", "fields", "format"} <= names
    assert {"400", "401", "403", "429"} <= set(listing["responses"])
    problem = listing["responses"]["401"]["content"]["application/problem+json"]["schema"]
    assert problem == {"$ref": "#/components/schemas/Problem"}

    people = doc["components"]["schemas"]["People"]["properties"]
    assert people["id"] == {"type": "integer"}
    assert people["created_at"] == {"type": "string", "format": "date-time"}  # DATETIME/datetime2 too
    assert "password_hash" not in people  # only allowlisted fields are described

    create = doc["paths"]["/people"]["post"]
    assert "201" in create["responses"] and "200" not in create["responses"]
    assert {p["name"] for p in create.get("parameters", [])} >= {"Idempotency-Key"}
    patch = doc["paths"]["/people/{item_id}"]["patch"]
    assert "412" in patch["responses"] and "If-Match" in {p["name"] for p in patch["parameters"]}
    validation = patch["responses"]["422"]["content"]["application/problem+json"]["schema"]
    assert validation == {"$ref": "#/components/schemas/Problem"}  # not FastAPI's own shape


def test_generated_python_client_works_against_the_api(db, monkeypatch):
    monkeypatch.setenv("PUBLIC_API_BASE", "https://api.example.com")
    from contractapi.core.config import get_settings

    get_settings.cache_clear()
    spec = parse_spec(_spec(db, [{**PEOPLE_EP, **WRITE, "etag_field": None}], read_only=False))
    source = build_python_sdk(spec, "crm")
    assert 'BASE_URL = os.environ.get("CONTRACTAPI_BASE_URL", "https://api.example.com/apis/crm")' in source
    assert export_openapi(spec, "crm")["servers"] == [{"url": "https://api.example.com/apis/crm", "description": "This API"}]

    sdk = types.ModuleType("crm_sdk")
    exec(compile(source, "crm_sdk.py", "exec"), sdk.__dict__)  # noqa: S102 — our own generated code
    sdk._client = TestClient(create_data_app(spec))  # same httpx API, no network
    sdk.API_KEY = KEY

    made = sdk.create_people({"name": "Barbara", "email": "b@example.com"}, idempotency_key="k-1")
    again = sdk.create_people({"name": "Barbara", "email": "b@example.com"}, idempotency_key="k-1")
    assert again["id"] == made["id"]  # a retry with the same key is not stored twice

    every = list(sdk.iter_people(limit=1))  # follows next-page links to the end
    assert len(every) == 5 and len({p["id"] for p in every}) == 5
    assert [p["name"] for p in sdk.iter_people(name__contains="barb")] == ["Barbara"]

    with pytest.raises(sdk.ApiError) as stale:
        sdk.update_people(made["id"], {"score": 2}, etag='"not-the-current-etag"')
    assert stale.value.status == 412 and stale.value.problem["type"].endswith("/precondition-failed")
    assert sdk.update_people(made["id"], {"score": 2})["score"] == 2
    sdk.delete_people(made["id"])
    with pytest.raises(sdk.ApiError) as gone:
        sdk.get_people(made["id"])
    assert gone.value.status == 404

    sdk.API_KEY = "wrong"
    with pytest.raises(sdk.ApiError) as denied:
        sdk.list_people()
    assert denied.value.status == 401
    import importlib.util

    if importlib.util.find_spec("pandas"):  # the DataFrame helper is optional
        sdk.API_KEY = KEY
        assert len(sdk.people_dataframe()) == 4


flags_meta = MetaData()
flags = Table(
    "mdb_flags",
    flags_meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("active", Boolean, nullable=False),
    Column("seen_at", DateTime),  # MySQL DATETIME / SQL Server DATETIME: was typed as a date
)
events = Table(  # no primary key, repeating values: like many analytics tables and views
    "mdb_events",
    flags_meta,
    Column("region", String(10), nullable=False),
    Column("amount", Integer, nullable=False),
)


@pytest.fixture
def extra_tables(db):
    engine = _engine(db)
    flags_meta.drop_all(engine)
    flags_meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(events.insert(), [{"region": r, "amount": a} for r, a in
                                       [("EU", 1), ("EU", 2), ("US", 3), ("EU", 4), ("US", 5)]])
    yield db
    flags_meta.drop_all(engine)


def test_booleans_and_datetimes_with_time_can_be_written(extra_tables):
    db = extra_tables
    ep = {"name": "flags", "path": "/flags", "table": "mdb_flags", "fields": ["id", "active", "seen_at"],
          "methods": ["GET", "POST", "PATCH"], "writable_fields": ["active", "seen_at"]}
    c = _client(db, [ep], read_only=False)
    made = c.post("/flags", json={"active": True, "seen_at": "2026-03-04T10:30:15"}, headers=H)
    assert made.status_code == 201, made.text
    assert made.json()["seen_at"].startswith("2026-03-04T10:30:15")  # the time is kept
    assert made.json()["active"] in (True, 1)  # MySQL BOOLEAN is TINYINT(1): 1
    changed = c.patch(f"/flags/{made.json()['id']}", json={"active": False}, headers=H)
    assert changed.status_code == 200 and changed.json()["active"] in (False, 0), changed.text


def test_an_id_that_is_not_unique_cannot_change_rows_or_drive_next_page_links(extra_tables):
    db = extra_tables
    base = {"name": "events", "path": "/events", "table": "mdb_events", "primary_key": "region",
            "fields": ["region", "amount"]}
    with pytest.raises(ValueError, match="could change many rows"):
        create_data_app(parse_spec(_spec(db, [{**base, "methods": ["GET", "DELETE"]}], read_only=False)))
    with pytest.raises(ValueError, match="next-page links need a unique id"):
        create_data_app(parse_spec(_spec(db, [base])))

    # Adding rows is fine, and page numbers walk every row exactly once (stable full sort).
    paged = {**base, "methods": ["GET", "POST"], "writable_fields": ["region", "amount"],
             "pagination": {"mode": "offset", "default_limit": 2, "max_limit": 2}}
    c = _client(db, [paged], read_only=False)
    assert c.post("/events", json={"region": "EU", "amount": 6}, headers=H).status_code == 201
    seen, offset = [], 0
    while True:
        page = c.get(f"/events?offset={offset}", headers=H).json()
        seen += [(i["region"], i["amount"]) for i in page["items"]]
        offset += 2
        if offset >= page["total"]:
            break
    assert sorted(seen) == sorted([("EU", 1), ("EU", 2), ("US", 3), ("EU", 4), ("US", 5), ("EU", 6)])


def test_compare_draft_flags_what_breaks_callers(db, monkeypatch, tmp_path):
    from contractapi.application.client_exports import compare_draft_with_saved
    from contractapi.core.config import get_settings
    from contractapi.infrastructure.persistence import spec_repo

    monkeypatch.setenv("SPECS_DIR", str(tmp_path / "specs"))
    get_settings.cache_clear()
    saved = _spec(db, [{**PEOPLE_EP, **WRITE}], read_only=False)
    spec_repo.save_spec("crm", saved)
    assert compare_draft_with_saved("crm", saved)["breaking"] is False

    narrower = {**PEOPLE_EP, **WRITE, "fields": [f for f in PEOPLE_EP["fields"] if f != "score"],
                "filters": ["name", "email", "tenant", "id"], "sortable": ["id", "name"],
                "writable_fields": ["name", "email"]}
    diff = compare_draft_with_saved("crm", _spec(db, [narrower], read_only=False))
    assert diff["breaking"] is True
    removed = {f for u in diff["updated"] for f in u["removed_fields"]}
    assert {"score", "?score", "body: score"} <= removed  # field, filter and input all reported
    listing = next(u for u in diff["updated"] if u["operation"] == "GET /people")
    assert "score" in listing["removed_fields"]  # a row field, not just the page wrapper
    assert compare_draft_with_saved("brand_new", saved)["breaking"] is False


def test_sorting_by_the_id_itself_works_with_page_numbers(db):
    # SQL Server rejected "ORDER BY id, id" (the id was added again as tie-breaker): 500 before.
    ep = {**PEOPLE_EP, "pagination": {"mode": "offset"}}
    c = _client(db, [ep])
    for sort in ("id", "-id", "name"):
        res = c.get(f"/people?sort={sort}", headers=H)
        assert res.status_code == 200, (sort, res.text)
    ids = [p["id"] for p in c.get("/people?sort=-id", headers=H).json()["items"]]
    assert ids == sorted(ids, reverse=True)
