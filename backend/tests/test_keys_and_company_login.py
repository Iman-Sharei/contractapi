"""API keys limited to some APIs and to reading; tokens from a company login server (OIDC/JWKS).
Every denial path is checked: other API → 403, read-only change → 403, expired → 401, forged
or foreign token → 401, login server down → 503."""

from __future__ import annotations

import json
import time

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from contractapi.application.data_api_builder import create_data_app
from contractapi.core.config import get_settings
from contractapi.domain.models.spec import parse_spec
from contractapi.infrastructure import api_keys
from contractapi.infrastructure.security import idp
from contractapi.interfaces.http.app_factory import create_studio_app

PG = "postgresql://postgres:postgres@localhost:5433/app"
EP = {
    "name": "customers", "path": "/customers", "table": "customers", "fields": ["id", "name", "email"],
    "methods": ["GET", "POST", "PATCH", "DELETE"], "writable_fields": ["name", "email"],
    "pagination": {"mode": "offset"},
}


def _pg_or_skip() -> None:
    try:
        with create_engine(PG.replace("postgresql://", "postgresql+psycopg://")).connect() as conn:
            conn.execute(text("SELECT 1 FROM customers LIMIT 1"))
    except Exception:
        pytest.skip("demo Postgres not reachable")


def _api(name: str, **app) -> TestClient:
    spec = parse_spec({"database": {"url": PG}, "endpoints": [EP], "app": {
        "api_prefix": "", "read_only": False, "auth": "api_key", "cache": {"enabled": False}, **app}})
    return TestClient(create_data_app(spec, name=name))


@pytest.fixture
def env(monkeypatch, tmp_path):
    _pg_or_skip()
    monkeypatch.setenv("SPECS_DIR", str(tmp_path / "specs"))
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("DATA_API_KEYS", "")  # only Studio keys in these tests
    get_settings.cache_clear()
    api_keys._cache = None
    api_keys._touched.clear()
    studio = TestClient(create_studio_app(), headers={"X-API-Key": get_settings().studio_api_key})
    for name in ("shop", "hr"):
        assert studio.post("/studio/specs", json={"name": name, "spec": {
            "database": {"url": PG}, "app": {"auth": "api_key"}, "endpoints": [{**EP, "methods": ["GET"]}]}}
        ).status_code == 200
    yield studio
    get_settings.cache_clear()


def _key(studio: TestClient, **body) -> str:
    res = studio.post("/studio/keys", json={"name": "app", **body})
    assert res.status_code == 200, res.text
    return res.json()["key"]


# ---------------------------------------------------------------- API keys


def test_a_key_opens_only_its_apis(env):
    shop_key = _key(env, apis=["shop"], access="write")
    every_key = _key(env, apis=["*"], access="read")
    shop, hr = _api("shop"), _api("hr")

    assert shop.get("/customers", headers={"X-API-Key": shop_key}).status_code == 200
    other = hr.get("/customers", headers={"X-API-Key": shop_key})
    assert other.status_code == 403 and "not allowed on the API 'hr'" in other.json()["detail"]
    assert hr.get("/customers", headers={"X-API-Key": every_key}).status_code == 200
    assert shop.get("/customers", headers={"X-API-Key": "dk_wrong"}).status_code == 401
    assert shop.get("/customers").status_code == 401


def test_a_read_only_key_reads_but_never_changes(env):
    read = {"X-API-Key": _key(env, apis=["shop"], access="read")}
    shop = _api("shop")
    assert shop.get("/customers", headers=read).status_code == 200
    for method, path, body in [("POST", "/customers", {"name": "x", "email": "x@x.io"}),
                               ("PATCH", "/customers/1", {"name": "y"}), ("DELETE", "/customers/1", None)]:
        res = shop.request(method, path, json=body, headers=read)
        assert res.status_code == 403 and "can only read" in res.json()["detail"], (method, res.text)

    pytest.importorskip("strawberry")
    query = shop.post("/graphql", json={"query": '{ endpoint(name: "customers", limit: 1) }'}, headers=read)
    assert query.status_code == 200 and query.json()["data"]["endpoint"]
    mutation = shop.post("/graphql", headers=read, json={
        "query": 'mutation { createItem(endpoint: "customers", data: {name: "x", email: "g@x.io"}) }'})
    assert mutation.json()["data"] is None and "can only read" in mutation.json()["errors"][0]["message"]


def test_expired_and_revoked_keys_are_refused(env):
    expired = api_keys.create_key(name="old", apis=["shop"], access="read", expires_at=time.time() - 1)
    shop = _api("shop")
    res = shop.get("/customers", headers={"X-API-Key": expired["key"]})
    assert res.status_code == 401 and res.json()["type"].endswith("/key-expired")
    assert "expired on" in res.json()["detail"]

    live = env.post("/studio/keys", json={"name": "soon", "apis": ["shop"], "access": "read"}).json()
    assert shop.get("/customers", headers={"X-API-Key": live["key"]}).status_code == 200
    assert env.delete(f"/studio/keys/{live['id']}").status_code == 200
    assert shop.get("/customers", headers={"X-API-Key": live["key"]}).status_code == 401  # at once


def test_keys_made_before_scopes_keep_working_as_their_creator_meant(env):
    rows = []
    for name, scopes in (("everything", ["*"]), ("reader", ["read"])):
        raw = f"dk_legacy_{name}_0123456789"
        rows.append({"id": name, "name": name, "prefix": raw[:10], "hash": api_keys._hash(raw),
                     "scopes": scopes, "created_at": time.time(), "revoked_at": None})
    api_keys._path().write_text(json.dumps(rows), encoding="utf-8")
    api_keys._cache = None
    hr = _api("hr")
    everything = {"X-API-Key": "dk_legacy_everything_0123456789"}
    reader = {"X-API-Key": "dk_legacy_reader_0123456789"}
    assert hr.get("/customers", headers=everything).status_code == 200  # all APIs, as before
    assert hr.get("/customers", headers=reader).status_code == 200
    assert hr.post("/customers", json={"name": "z", "email": "z@x.io"}, headers=reader).status_code == 403
    listed = {k["name"]: k for k in env.get("/studio/keys").json()["keys"]}
    assert listed["everything"]["apis"] == ["*"] and listed["reader"]["access"] == "read"


def test_last_use_is_recorded_without_a_write_per_request(env):
    key = _key(env, apis=["shop"], access="read")
    shop = _api("shop")
    assert env.get("/studio/keys").json()["keys"][0]["last_used_at"] is None
    shop.get("/customers", headers={"X-API-Key": key})
    first = env.get("/studio/keys").json()["keys"][0]["last_used_at"]
    assert first is not None
    stamp = api_keys._path().stat().st_mtime_ns
    shop.get("/customers", headers={"X-API-Key": key})
    assert api_keys._path().stat().st_mtime_ns == stamp  # same minute: no file write


def test_studio_asks_which_apis_a_key_is_for(env):
    assert env.post("/studio/keys", json={"name": "x"}).status_code == 422  # least privilege
    assert env.post("/studio/keys", json={"name": "x", "apis": []}).status_code == 422
    unknown = env.post("/studio/keys", json={"name": "x", "apis": ["nope"]})
    assert unknown.status_code == 422 and "No saved API named 'nope'" in unknown.json()["detail"]
    assert env.post("/studio/keys", json={"name": "x", "apis": ["shop"], "access": "admin"}).status_code == 422
    legacy = env.post("/studio/keys", json={"name": "cli", "scopes": ["*"]})  # older scripts
    assert legacy.status_code == 200 and legacy.json()["apis"] == ["*"] and legacy.json()["access"] == "write"
    made = env.post("/studio/keys", json={"name": "bi", "apis": ["shop", "hr"], "expires_in_days": 30}).json()
    assert made["apis"] == ["hr", "shop"] and made["access"] == "read"
    assert 29 * 86_400 < made["expires_at"] - time.time() <= 30 * 86_400
    from contractapi.infrastructure.audit import recent_events

    created = [e for e in recent_events(20) if e["action"] == "studio.key.create"][-1]
    assert created["meta"]["apis"] == ["hr", "shop"] and made["key"] not in json.dumps(created)


# ---------------------------------------------------------------- company login (OIDC)

ISSUER = "https://login.example.com/realms/main"
JWKS = f"{ISSUER}/protocol/openid-connect/certs"


def _rsa():
    from cryptography.hazmat.primitives.asymmetric import rsa

    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk(private, kid: str) -> dict:
    data = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    return {**data, "kid": kid, "use": "sig", "alg": "RS256"}


@pytest.fixture
def login_server(monkeypatch):
    """A fake company login server: discovery + JWKS, counting how often keys are fetched."""
    pytest.importorskip("cryptography")
    state = {"keys": [], "fetches": 0, "down": False}
    signing = _rsa()
    state["keys"] = [_jwk(signing, "k1")]

    def fetch(url: str, timeout: float = 5.0) -> dict:
        if state["down"]:
            raise idp.LoginServerUnreachable(f"{url}: connection refused")
        if url == f"{ISSUER}/.well-known/openid-configuration":
            return {"issuer": ISSUER, "jwks_uri": JWKS}
        if url == JWKS:
            state["fetches"] += 1
            return {"keys": list(state["keys"])}
        raise idp.LoginServerUnreachable(url)

    monkeypatch.setattr(idp, "fetch_json", fetch)
    for cache in (idp._discovery, idp._keys, idp._last_fetch):
        cache.clear()
    state["signing"] = signing
    return state


def _token(private, *, kid="k1", alg="RS256", **claims) -> str:
    body = {"iss": ISSUER, "aud": "orders-api", "sub": "ada", "exp": int(time.time()) + 300,
            "realm_access": {"roles": ["analyst"]}, **claims}
    return jwt.encode(body, private, algorithm=alg, headers={"kid": kid})


def _login_api() -> TestClient:
    spec = parse_spec({"database": {"url": PG}, "endpoints": [{**EP, "methods": ["GET"], "roles": ["analyst"]}],
                       "app": {"api_prefix": "", "auth": "jwt", "cache": {"enabled": False}, "jwt": {
                           "provider": "oidc", "issuer": ISSUER, "audience": "orders-api",
                           "roles_claim": "realm_access.roles"}}})
    return TestClient(create_data_app(spec, name="orders"))


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_company_login_tokens_are_accepted_with_their_roles(login_server):
    _pg_or_skip()
    api = _login_api()
    signing = login_server["signing"]
    assert api.get("/customers", headers=_bearer(_token(signing))).status_code == 200
    viewer = api.get("/customers", headers=_bearer(_token(signing, realm_access={"roles": ["viewer"]})))
    assert viewer.status_code == 403  # the endpoint needs the analyst role
    assert api.get("/customers").status_code == 401
    assert api.post("/auth/refresh", json={"refresh_token": "x"}).status_code in (404, 405)


@pytest.mark.parametrize(
    ("claims", "problem"),
    [
        ({"aud": "other-app"}, "another application"),
        ({"iss": "https://evil.example.com"}, "another login server"),
        ({"exp": int(time.time()) - 120}, "expired"),
    ],
)
def test_tokens_for_other_apps_servers_or_times_are_refused(login_server, claims, problem):
    _pg_or_skip()
    res = _login_api().get("/customers", headers=_bearer(_token(login_server["signing"], **claims)))
    assert res.status_code == 401 and problem in res.json()["detail"], res.text


def test_forged_and_downgraded_tokens_are_refused(login_server, monkeypatch):
    _pg_or_skip()
    api = _login_api()
    forged = _token(_rsa())  # right kid, wrong private key
    assert api.get("/customers", headers=_bearer(forged)).status_code == 401
    shared = jwt.encode({"iss": ISSUER, "aud": "orders-api", "exp": int(time.time()) + 60,
                         "realm_access": {"roles": ["analyst"]}}, get_settings().jwt_secret, algorithm="HS256")
    assert api.get("/customers", headers=_bearer(shared)).status_code == 401  # no HS* downgrade
    unsigned = jwt.encode({"iss": ISSUER, "aud": "orders-api"}, None, algorithm="none")
    assert api.get("/customers", headers=_bearer(unsigned)).status_code == 401
    assert api.get("/customers", headers=_bearer("not-a-token")).status_code == 401


def test_rotated_keys_are_picked_up_but_unknown_kids_cannot_flood_the_server(login_server, monkeypatch):
    _pg_or_skip()
    api = _login_api()
    assert api.get("/customers", headers=_bearer(_token(login_server["signing"]))).status_code == 200
    assert login_server["fetches"] == 1
    for _ in range(5):  # random kids: refused, and no extra fetch within 30 s of the last one
        assert api.get("/customers", headers=_bearer(_token(_rsa(), kid="random"))).status_code == 401
    assert login_server["fetches"] == 1

    monkeypatch.setattr(idp, "REFETCH_GAP", 0)
    newer = _rsa()
    login_server["keys"].append(_jwk(newer, "k2"))  # the company rotates its keys
    assert api.get("/customers", headers=_bearer(_token(newer, kid="k2"))).status_code == 200


def test_an_unreachable_login_server_is_503_not_a_silent_pass(login_server):
    _pg_or_skip()
    login_server["down"] = True
    res = _login_api().get("/customers", headers=_bearer(_token(login_server["signing"])))
    assert res.status_code == 503 and res.json()["type"].endswith("/auth-unavailable")


def test_studio_tests_the_login_server_and_will_not_mint_its_tokens(login_server, monkeypatch, tmp_path):
    monkeypatch.setenv("SPECS_DIR", str(tmp_path))
    get_settings.cache_clear()
    studio = TestClient(create_studio_app(), headers={"X-API-Key": get_settings().studio_api_key})
    ok = studio.post("/studio/company-login/test", json={"issuer": ISSUER})
    assert ok.status_code == 200, ok.text
    assert ok.json() == {"issuer": ISSUER, "jwks_uri": JWKS, "signing_keys": 1, "algorithms": ["RS256"]}
    plain = studio.post("/studio/company-login/test", json={"issuer": "http://login.example.com"})
    assert plain.status_code == 422 and "https://" in plain.json()["detail"]
    login_server["down"] = True
    down = studio.post("/studio/company-login/test", json={"issuer": "https://other.example.com"})
    assert down.status_code == 400 and "Could not read" in down.json()["detail"]
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("jwt_cfg", "message"),
    [
        ({"provider": "oidc", "issuer": "http://login.example.com", "audience": "a"}, "must use https://"),
        ({"provider": "oidc", "issuer": "not a url", "audience": "a"}, "web address"),
        ({"provider": "oidc", "issuer": ISSUER, "audience": " "}, "audience"),
        ({"algorithm": "RS256"}, "provider: oidc"),
        ({"roles_claim": "realm_access..roles"}, "roles_claim"),
    ],
)
def test_login_settings_are_checked_with_actionable_messages(jwt_cfg, message):
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match=message):
        parse_spec({"database": {"url": PG}, "app": {"auth": "jwt", "jwt": jwt_cfg}, "endpoints": [EP]})


def test_local_login_servers_may_use_http_for_testing():
    for issuer in ("http://localhost:8080/realms/dev", "http://keycloak:8080/realms/dev",
                   "http://host.docker.internal:8080/realms/dev"):
        parse_spec({"database": {"url": PG}, "endpoints": [{**EP, "methods": ["GET"]}],
                    "app": {"auth": "jwt", "jwt": {"provider": "oidc", "issuer": issuer, "audience": "a"}}})


def test_company_login_example_round_trips_through_yaml():
    from pathlib import Path

    import yaml

    from contractapi.domain.models.spec import dump_spec, load_spec

    spec = load_spec(Path(__file__).parent.parent / "examples" / "company_login.yaml")
    assert spec.app.jwt.provider == "oidc" and spec.app.jwt.roles_claim == "realm_access.roles"
    assert parse_spec(yaml.safe_load(dump_spec(spec))).model_dump() == spec.model_dump()
