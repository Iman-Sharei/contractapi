"""OIDC / JWKS verification for Studio control-plane (enterprise IdP)."""

from __future__ import annotations

import time
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

from dataapi.core.config import Settings, get_settings
from dataapi.core.errors import AppError
from dataapi.core.logging import get_logger

logger = get_logger("dataapi.oidc")

_jwks_clients: dict[str, PyJWKClient] = {}
_discovery_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def oidc_enabled(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(s.studio_oidc_issuer.strip()) and s.experimental_enabled("oidc")


def _discover(issuer: str) -> dict[str, Any]:
    now = time.time()
    cached = _discovery_cache.get(issuer)
    if cached and cached[0] > now:
        return cached[1]
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    import urllib.request

    with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
        import json

        data = json.loads(resp.read().decode("utf-8"))
    _discovery_cache[issuer] = (now + 3600, data)
    return data


def _jwks_client(settings: Settings) -> PyJWKClient:
    jwks_url = settings.studio_oidc_jwks_url.strip()
    if not jwks_url:
        meta = _discover(settings.studio_oidc_issuer.strip())
        jwks_url = meta.get("jwks_uri") or ""
    if not jwks_url:
        raise AppError(
            type_="https://dataapi.dev/problems/misconfigured",
            title="OIDC misconfigured",
            status=500,
            detail="Could not resolve JWKS URL for studio OIDC issuer.",
        )
    if jwks_url not in _jwks_clients:
        _jwks_clients[jwks_url] = PyJWKClient(jwks_url, cache_keys=True)
    return _jwks_clients[jwks_url]


def verify_studio_oidc_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    """Validate Bearer access/ID token against configured IdP JWKS."""
    s = settings or get_settings()
    if not oidc_enabled(s):
        raise AppError(
            type_="https://dataapi.dev/problems/misconfigured",
            title="OIDC disabled",
            status=500,
            detail="Studio OIDC is not configured.",
        )
    try:
        client = _jwks_client(s)
        signing_key = client.get_signing_key_from_jwt(token)
        options = {"verify_aud": bool(s.studio_oidc_audience.strip())}
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256", "PS256"],
            audience=s.studio_oidc_audience.strip() or None,
            issuer=s.studio_oidc_issuer.strip(),
            options=options,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("OIDC token rejected: %s", exc.__class__.__name__)
        raise AppError(
            type_="https://dataapi.dev/problems/unauthorized",
            title="Unauthorized",
            status=401,
            detail="Invalid or expired OIDC token.",
        ) from exc

    allow = {e.strip().lower() for e in s.studio_oidc_email_allowlist.split(",") if e.strip()}
    if allow:
        email = (claims.get("email") or claims.get("preferred_username") or "").lower()
        if email not in allow:
            raise AppError(
                type_="https://dataapi.dev/problems/forbidden",
                title="Forbidden",
                status=403,
                detail="OIDC subject not on Studio allowlist.",
            )
    return {
        "sub": claims.get("sub"),
        "email": claims.get("email"),
        "roles": claims.get("roles") or claims.get("realm_access", {}).get("roles") or [],
        "auth_mode": "oidc",
        "claims": claims,
    }


@lru_cache
def _settings_fingerprint() -> str:
    s = get_settings()
    return f"{s.studio_oidc_issuer}|{s.studio_oidc_jwks_url}|{s.studio_oidc_audience}"
