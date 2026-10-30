import pytest
from pydantic import ValidationError

from dataapi.domain.models.spec import ApiSpec, EndpointSpec, load_spec


def test_rejects_sensitive_fields_by_default():
    with pytest.raises(ValidationError) as exc:
        EndpointSpec(
            name="users",
            path="/users",
            table="users",
            fields=["id", "email", "password_hash"],
        )
    assert "password_hash" in str(exc.value)


def test_allows_sensitive_when_forced():
    ep = EndpointSpec(
        name="users",
        path="/users",
        table="users",
        fields=["id", "password_hash"],
        allow_sensitive=True,
    )
    assert "password_hash" in ep.fields


def test_read_only_blocks_writes():
    with pytest.raises(ValidationError):
        ApiSpec.model_validate(
            {
                "database": {"url": "postgresql://localhost/db"},
                "app": {"read_only": True},
                "endpoints": [
                    {
                        "name": "customers",
                        "path": "/customers",
                        "table": "customers",
                        "methods": ["GET", "POST"],
                        "fields": ["id", "name"],
                    }
                ],
            }
        )


def test_filters_must_be_subset_of_fields():
    with pytest.raises(ValidationError):
        EndpointSpec(
            name="customers",
            path="/customers",
            table="customers",
            fields=["id", "name"],
            filters=["email"],
        )


def test_path_normalized(tmp_path):
    path = tmp_path / "spec.yaml"
    path.write_text(
        """
database:
  url: postgresql://localhost/db
endpoints:
  - name: customers
    path: customers
    table: customers
    fields: [id, name]
""",
        encoding="utf-8",
    )
    spec = load_spec(path)
    assert spec.endpoints[0].path == "/customers"


def test_duplicate_paths_rejected():
    with pytest.raises(ValidationError):
        ApiSpec.model_validate(
            {
                "database": {"url": "postgresql://localhost/db"},
                "endpoints": [
                    {
                        "name": "a",
                        "path": "/customers",
                        "table": "customers",
                        "fields": ["id", "name"],
                    },
                    {
                        "name": "b",
                        "path": "/customers",
                        "table": "clients",
                        "fields": ["id", "name"],
                    },
                ],
            }
        )


def test_endpoint_name_pattern():
    with pytest.raises(ValidationError):
        EndpointSpec(
            name="Bad Name",
            path="/x",
            table="x",
            fields=["id"],
        )
