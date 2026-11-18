"""Studio operations routes: API keys, audit log, test tokens."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from contractapi.application.studio_service import (
    spec_store,
)
from contractapi.core.errors import AppError
from contractapi.infrastructure.security.jwt_tokens import issue_token
from contractapi.interfaces.http.studio.schemas import (
    IssueTokenRequest,
)

# Included by studio.router under /studio with its auth dependency.
router = APIRouter()


@router.post("/token")
def studio_issue_token(body: IssueTokenRequest) -> dict[str, str]:
    """Mint a JWT for testing data-plane auth=jwt (admin-only; uses the target API's jwt config)."""
    from contractapi.domain.models.spec import JwtConfig

    target = spec_store.get(body.api) if body.api else spec_store.active
    if body.api and target is None:
        raise AppError(
            type_="https://contractapi.dev/problems/not-found",
            title="Not Found",
            status=404,
            detail=f"No activated API named '{body.api}'. Activate it first.",
        )
    token = issue_token(
        subject=body.sub,
        roles=body.roles,
        jwt_cfg=target.app.jwt if target else JwtConfig(),
        expires_minutes=body.expires_minutes,
        extra=dict(body.claims) or None,
    )
    return {"access_token": token, "token_type": "bearer"}


@router.get("/keys")
def studio_list_keys() -> dict[str, Any]:
    from contractapi.infrastructure.api_keys import list_keys

    return {"keys": list_keys()}


@router.post("/keys")
def studio_create_key(body: dict[str, Any]) -> dict[str, Any]:
    from contractapi.infrastructure.api_keys import create_key

    name = str(body.get("name") or "default")
    scopes = list(body.get("scopes") or ["*"])
    return create_key(name=name, scopes=scopes)


@router.delete("/keys/{key_id}")
def studio_revoke_key(key_id: str) -> dict[str, bool]:
    from contractapi.infrastructure.api_keys import revoke_key

    ok = revoke_key(key_id)
    if not ok:
        raise AppError(
            type_="https://contractapi.dev/problems/not-found",
            title="Not Found",
            status=404,
            detail=f"Key {key_id} not found or already revoked",
        )
    return {"revoked": True}


@router.get("/audit")
def studio_audit(limit: int = 100) -> dict[str, Any]:
    from contractapi.infrastructure.audit import recent_events

    return {"events": recent_events(limit=min(max(limit, 1), 500))}
