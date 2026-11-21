"""Authentication helpers for studio and data planes."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
from typing import Annotated, Any

from fastapi import Header, Request

from contractapi.core.config import get_settings
from contractapi.core.errors import AppError
from contractapi.domain.models.spec import ApiSpec, AuthMode
from contractapi.infrastructure.security.jwt_tokens import extract_bearer, verify_token


def _constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _actor(claims: dict[str, Any]) -> dict[str, Any]:
    """Who is acting in Studio, for the audit trail (never the token itself)."""
    who = claims.get("email") or claims.get("preferred_username") or claims.get("sub") or "oidc-user"
    return {"sub": str(who), "roles": ["studio"]}


def studio_actor(request: Request) -> dict[str, Any]:
    return getattr(request.state, "studio_actor", None) or {"sub": "studio", "roles": ["studio"]}


def require_studio_api_key(
    request: Request,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """
    Studio auth: X-API-Key (break-glass / CLI), Bearer OIDC, or httpOnly OIDC cookie.
    """
    settings = get_settings()
    if x_api_key and _constant_time_equals(x_api_key, settings.studio_api_key):
        request.state.studio_actor = {"sub": "studio-key", "roles": ["studio"]}
        return "api_key"

    from contractapi.infrastructure.security.oidc import (
        oidc_cookie_name,
        oidc_enabled,
        verify_studio_oidc_token,
    )

    if oidc_enabled(settings) and authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            request.state.studio_actor = _actor(verify_studio_oidc_token(token.strip(), settings))
            return "oidc"

    if oidc_enabled(settings):
        cookie_token = request.cookies.get(oidc_cookie_name(settings))
        if cookie_token:
            request.state.studio_actor = _actor(verify_studio_oidc_token(cookie_token, settings))
            return "oidc_cookie"

    detail = "Missing or invalid X-API-Key for studio."
    if oidc_enabled(settings):
        detail = "Provide X-API-Key, OIDC Bearer token, or OIDC session cookie."
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


def _parse_networks(entries: list[str]) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    nets = []
    for entry in entries:
        raw = entry.strip()
        if raw.endswith("."):  # legacy "10.0.0." prefix form → 10.0.0.0/24-style
            octets = raw.rstrip(".").split(".")
            raw = ".".join(octets + ["0"] * (4 - len(octets))) + f"/{8 * len(octets)}"
        try:
            nets.append(ipaddress.ip_network(raw, strict=False))
        except ValueError:
            continue
    return nets


def _in_networks(ip: str, entries: list[str]) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in _parse_networks(entries))


def client_ip(request: Request) -> str:
    """Peer address; X-Forwarded-For is honored only when the peer is a trusted proxy."""
    peer = request.client.host if request.client else ""
    trusted = [p for p in get_settings().trusted_proxies.split(",") if p.strip()]
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded and trusted and _in_networks(peer, trusted):
        # Rightmost address not belonging to our proxies is the real client.
        for hop in reversed([h.strip() for h in forwarded.split(",") if h.strip()]):
            if not _in_networks(hop, trusted):
                return hop
    return peer


def enforce_ip_allowlist(request: Request, allowlist: list[str]) -> None:
    if not allowlist:
        return
    ip = client_ip(request)
    if _in_networks(ip, allowlist):
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

        if not keys and not any(not k["revoked"] for k in list_keys()):
            # Fail closed: api_key mode with zero keys must not mean "open".
            raise AppError(
                type_="https://contractapi.dev/problems/unauthorized",
                title="Unauthorized",
                status=401,
                detail=(
                    "This API requires an API key, but none is configured. "
                    "Create one in Studio → Ops → API keys (or set DATA_API_KEYS), "
                    "or set auth: none for a public read-only API."
                ),
            )
        enforce_data_api_key(request, keys)
        provided = request.headers.get("X-API-Key") or ""
        return {
            # Never use (part of) the secret as identity: it ends up in audit/logs.
            "sub": "key:" + hashlib.sha256(provided.encode()).hexdigest()[:12],
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
