from dataapi.application.postman_export import build_postman_collection
from dataapi.domain.models.spec import parse_spec
from dataapi.infrastructure.api_keys import create_key, key_is_valid, revoke_key


def test_api_key_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("SPECS_DIR", str(tmp_path / "specs"))
    from dataapi.core.config import get_settings

    get_settings.cache_clear()
    created = create_key(name="t", scopes=["read"])
    assert created["key"].startswith("dk_")
    assert key_is_valid(created["key"])
    assert revoke_key(created["id"]) is True
    assert key_is_valid(created["key"]) is False
    get_settings.cache_clear()


def test_postman_and_sql_params_spec():
    spec = parse_spec(
        {
            "database": {"url": "postgresql://x/y"},
            "app": {"auth": "api_key", "read_only": True, "webhooks": []},
            "endpoints": [
                {
                    "name": "metrics",
                    "path": "/metrics/x",
                    "sql": "SELECT 1 AS id, :min_total::float AS total",
                    "sql_params": [{"name": "min_total", "type": "float", "required": True}],
                    "fields": ["id", "total"],
                    "primary_key": "id",
                }
            ],
        }
    )
    assert spec.endpoints[0].is_sql
    coll = build_postman_collection(spec)
    assert coll["info"]["name"]
    assert coll["item"]
