from fastapi.testclient import TestClient

from dataapi.core.config import get_settings
from dataapi.interfaces.http.app_factory import create_studio_app


def test_studio_requires_api_key():
    get_settings.cache_clear()
    client = TestClient(create_studio_app())
    res = client.post("/studio/validate", json={"spec": {}, "check_db": False})
    assert res.status_code == 401
    assert res.headers["content-type"].startswith("application/problem+json")


def test_studio_validate_invalid_spec():
    get_settings.cache_clear()
    settings = get_settings()
    client = TestClient(create_studio_app())
    res = client.post(
        "/studio/validate",
        headers={"X-API-Key": settings.studio_api_key},
        json={
            "check_db": False,
            "spec": {
                "database": {"url": "postgresql://localhost/db"},
                "endpoints": [
                    {
                        "name": "users",
                        "path": "/users",
                        "table": "users",
                        "fields": ["id", "password_hash"],
                    }
                ],
            },
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["valid"] is False
    assert any("password_hash" in e for e in body["errors"])


def test_health():
    client = TestClient(create_studio_app())
    assert client.get("/health").json()["status"] == "ok"
