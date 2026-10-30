from contractapi.infrastructure.persistence import spec_repo


def test_save_list_load_delete(tmp_path, monkeypatch):
    monkeypatch.setenv("SPECS_DIR", str(tmp_path))
    from contractapi.core.config import get_settings

    get_settings.cache_clear()

    raw = {
        "database": {"url": "postgresql://localhost/db"},
        "app": {"read_only": True, "auth": "none"},
        "endpoints": [
            {
                "name": "customers",
                "path": "/customers",
                "table": "customers",
                "fields": ["id", "name"],
            }
        ],
    }
    spec_repo.save_spec("demo", raw)
    listed = spec_repo.list_specs()
    assert any(i["name"] == "demo" for i in listed)
    loaded = spec_repo.read_spec("demo")
    assert loaded.endpoints[0].name == "customers"
    spec_repo.delete_spec("demo")
    assert spec_repo.list_specs() == []
    get_settings.cache_clear()
