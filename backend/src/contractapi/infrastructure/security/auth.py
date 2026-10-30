"""Authentication helpers for studio and data planes."""

from __future__ import annotations

import hmac
from typing import Annotated, Any

from fastapi import Header, Request

from contractapi.core.config import get_settings
from contractapi.core.errors import AppError
from contractapi.domain.models.spec import ApiSpec, AuthMode
from contractapi.infrastructure.security.jwt_tokens import extract_bearer, verify_token


def _constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def require_studio_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """
    Studio auth: X-API-Key (break-glass / CLI) OR Bearer OIDC token when configured.
    """
    settings = get_settings()
    if x_api_key and _constant_time_equals(x_api_key, settings.studio_api_key):
        return "api_key"

    from contractapi.infrastructure.security.oidc import oidc_enabled, verify_studio_oidc_token

    if oidc_enabled(settings) and authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            verify_studio_oidc_token(token.strip(), settings)
            return "oidc"

    detail = "Missing or invalid X-API-Key for studio."
    if oidc_enabled(settings):
        detail = "Provide X-API-Key or a valid OIDC Bearer token."
    raise AppError(
        type_="https://contractapi.dev/problems/unauthorized",
        title="Unauthorized",
        status=401,
        detail=detail,
    )


def enforce_data_api_key(request: Request, required_keys: set[str]) -> None:
    provided = request.headers.get("X-API-Key")
    if not provided:
        raise AppError(
            type_="https://contractapi.dev/problems/unauthorized",
            title="Unauthorized",
            status=401,
            detail="Valid X-API-Key required.",
        )
    from contractapi.infrastructure.api_keys import key_is_valid

    if any(_constant_time_equals(provided, k) for k in required_keys) or key_is_valid(provided):
        return
    raise AppError(
        type_="https://contractapi.dev/problems/unauthorized",
        title="Unauthorized",
        status=401,
        detail="Valid X-API-Key required.",
    )


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return ""


def enforce_ip_allowlist(request: Request, allowlist: list[str]) -> None:
    if not allowlist:
        return
    ip = _client_ip(request)
    if ip in allowlist or ip == "testclient":
        return
    # naive CIDR: prefix match for x.x.x.0/24 style written as "10.0.0."
    for entry in allowlist:
        if entry.endswith(".") and ip.startswith(entry):
            return
        if "/" in entry:
            # simple prefix before /
            base = entry.split("/")[0].rsplit(".", 1)[0] + "."
            if ip.startswith(base):
                return
    raise AppError(
        type_="https://contractapi.dev/problems/forbidden",
        title="Forbidden",
        status=403,
        detail="Client IP not allowlisted.",
        extensions={"ip": ip},
    )


def authenticate_request(request: Request, spec: ApiSpec) -> dict[str, Any]:
    """Return principal context: {sub, roles, auth_mode}."""
    settings = get_settings()
    enforce_ip_allowlist(request, list(spec.app.ip_allowlist or []))

    if spec.app.auth == AuthMode.NONE:
        return {"sub": "anonymous", "roles": ["anonymous"], "auth_mode": "none"}

    if spec.app.auth == AuthMode.API_KEY:
        keys = settings.data_api_key_set
        from contractapi.infrastructure.api_keys import list_keys

        managed = list_keys()
        if keys or managed:
            enforce_data_api_key(request, keys)
        return {
            "sub": (request.headers.get("X-API-Key") or "api-key-client")[:16],
            "roles": ["api_client"],
            "auth_mode": "api_key",
        }

    # JWT
    token = extract_bearer(request.headers.get("Authorization"))
    if not token:
        raise AppError(
            type_="https://contractapi.dev/problems/unauthorized",
            title="Unauthorized",
            status=401,
            detail="Bearer JWT required.",
        )
    claims = verify_token(token, spec.app.jwt)
    roles = claims.get("roles") or []
    if isinstance(roles, str):
        roles = [roles]
    if not isinstance(roles, list):
        roles = []
    return {
        "sub": str(claims.get("sub", "")),
        "roles": [str(r) for r in roles],
        "auth_mode": "jwt",
        "claims": claims,
    }


def enforce_endpoint_roles(principal: dict[str, Any], allowed_roles: list[str]) -> None:
    if not allowed_roles:
        return
    principal_roles = set(principal.get("roles") or [])
    if principal_roles.isdisjoint(set(allowed_roles)):
        raise AppError(
            type_="https://contractapi.dev/problems/forbidden",
            title="Forbidden",
            status=403,
            detail="Role not permitted for this endpoint.",
            extensions={"required_roles": allowed_roles},
        )
