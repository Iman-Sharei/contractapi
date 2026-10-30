import pytest
from pydantic import ValidationError

from contractapi.core.config import get_settings
from contractapi.domain.models.spec import ApiSpec, JwtConfig, PaginationMode
from contractapi.infrastructure.security.jwt_tokens import issue_token, verify_token


def test_cursor_mode_auto_adds_pk_sortable():
    ep = ApiSpec.model_validate(
        {
            "database": {"url": "postgresql://localhost/db"},
            "endpoints": [
                {
                    "name": "customers",
                    "path": "/customers",
                    "table": "customers",
                    "fields": ["id", "name"],
                    "sortable": ["name"],
                    "pagination": {"mode": "cursor"},
                }
            ],
        }
    ).endpoints[0]
    assert ep.pagination.mode == PaginationMode.CURSOR
    assert "id" in ep.sortable


def test_rbac_unknown_field_rejected():
    with pytest.raises(ValidationError):
        ApiSpec.model_validate(
            {
                "database": {"url": "postgresql://localhost/db"},
                "app": {
                    "rbac": [
                        {"role": "viewer", "endpoints": {"customers": ["id", "secret"]}}
                    ]
                },
                "endpoints": [
                    {
                        "name": "customers",
                        "path": "/customers",
                        "table": "customers",
                        "fields": ["id", "name"],
                    }
                ],
            }
        )


def test_jwt_roundtrip():
    get_settings.cache_clear()
    token = issue_token(subject="iman", roles=["analyst"], jwt_cfg=JwtConfig())
    claims = verify_token(token, JwtConfig())
    assert claims["sub"] == "iman"
    assert "analyst" in claims["roles"]
