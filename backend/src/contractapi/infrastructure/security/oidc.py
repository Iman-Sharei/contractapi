"""OIDC / JWKS verification for Studio control-plane (enterprise IdP)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import jwt
from jwt import PyJWKClient

from contractapi.core.config import Settings, get_settings
from contractapi.core.errors import AppError
from contractapi.core.logging import get_logger

logger = get_logger("contractapi.oidc")

_jwks_clients: dict[str, PyJWKClient] = {}
_discovery_cache: dict[str, tuple[float, dict[str, Any]]] = {}
DEFAULT_OIDC_COOKIE = "contractapi_oidc"


def oidc_enabled(settings: Settings | None = None) -> bool:
    """GA: enabled whenever STUDIO_OIDC_ISSUER is set (no experimental gate)."""
    s = settings or get_settings()
    return bool(s.studio_oidc_issuer.strip())


def oidc_browser_enabled(settings: Settings | None = None) -> bool:
    """Cookie login needs issuer + client_id + redirect_uri."""
    s = settings or get_settings()
    return bool(
        s.studio_oidc_issuer.strip()
        and s.studio_oidc_client_id.strip()
        and s.studio_oidc_redirect_uri.strip()
    )


def oidc_cookie_name(settings: Settings | None = None) -> str:
    s = settings or get_settings()
    return (s.studio_oidc_cookie_name or DEFAULT_OIDC_COOKIE).strip() or DEFAULT_OIDC_COOKIE


def oidc_discovery(issuer: str) -> dict[str, Any]:
    return _discover(issuer)


def _discover(issuer: str) -> dict[str, Any]:
    now = time.time()
    cached = _discovery_cache.get(issuer)
    if cached and cached[0] > now:
        return cached[1]
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    with urllib.request.urlopen(url, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    _discovery_cache[issuer] = (now + 3600, data)
    return data


def exchange_code_for_tokens(
    code: str, settings: Settings | None = None, *, code_verifier: str | None = None
) -> dict[str, Any]:
    """Authorization-code exchange for browser OIDC cookie login."""
    s = settings or get_settings()
    if not oidc_browser_enabled(s):
        raise AppError(
            type_="https://contractapi.dev/problems/misconfigured",
            title="OIDC browser login disabled",
            status=503,
            detail="OIDC client_id / redirect_uri not configured.",
        )
    meta = _discover(s.studio_oidc_issuer.strip())
    token_url = meta.get("token_endpoint")
    if not token_url:
        raise AppError(
            type_="https://contractapi.dev/problems/misconfigured",
            title="OIDC misconfigured",
            status=500,
            detail="token_endpoint missing from discovery document.",
        )
    body = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": s.studio_oidc_redirect_uri.strip(),
            "client_id": s.studio_oidc_client_id.strip(),
            **({"client_secret": s.studio_oidc_client_secret} if s.studio_oidc_client_secret else {}),
            **({"code_verifier": code_verifier} if code_verifier else {}),
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        token_url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise AppError(
            type_="https://contractapi.dev/problems/unauthorized",
            title="Unauthorized",
            status=401,
            detail=f"Token exchange failed at the identity provider: {detail}",
        ) from exc


def _jwks_client(settings: Settings) -> PyJWKClient:
    jwks_url = settings.studio_oidc_jwks_url.strip()
    if not jwks_url:
        meta = _discover(settings.studio_oidc_issuer.strip())
        jwks_url = meta.get("jwks_uri") or ""
    if not jwks_url:
        raise AppError(
            type_="https://contractapi.dev/problems/misconfigured",
            title="OIDC misconfigured",
            status=500,
            detail="Could not resolve JWKS URL for studio OIDC issuer.",
        )
    if jwks_url not in _jwks_clients:
        _jwks_clients[jwks_url] = PyJWKClient(jwks_url, cache_keys=True)
    return _jwks_clients[jwks_url]


def _issued_for_client(claims: dict[str, Any], client_id: str) -> bool:
    if not client_id:
        return False
    aud = claims.get("aud")
    auds = aud if isinstance(aud, list) else [aud]
    return client_id in auds or claims.get("azp") == client_id


def oidc_config_problems(settings: Settings | None = None) -> list[str]:
    s = settings or get_settings()
    if not oidc_enabled(s):
        return []
    if not s.studio_oidc_audience.strip() and not s.studio_oidc_client_id.strip():
        return [
            (
                "STUDIO_OIDC_ISSUER is set but neither STUDIO_OIDC_AUDIENCE nor "
                "STUDIO_OIDC_CLIENT_ID is: any token from that issuer would be accepted"
            )
        ]
    return []


def pkce_pair() -> tuple[str, str]:
    """(code_verifier, S256 code_challenge) per RFC 7636."""
    import base64
    import hashlib
    import secrets

    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def verify_studio_oidc_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    """Validate Bearer access/ID token against configured IdP JWKS."""
    s = settings or get_settings()
    if not oidc_enabled(s):
        raise AppError(
            type_="https://contractapi.dev/problems/misconfigured",
            title="OIDC disabled",
            status=500,
            detail="Studio OIDC is not configured.",
        )
    try:
        client = _jwks_client(s)
        signing_key = client.get_signing_key_from_jwt(token)
        audience = s.studio_oidc_audience.strip()
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256", "PS256"],
            audience=audience or None,
            issuer=s.studio_oidc_issuer.strip(),
            options={"verify_aud": bool(audience)},
        )
        if not audience and not _issued_for_client(claims, s.studio_oidc_client_id.strip()):
            # Without an audience check any token from this issuer (e.g. any Google
            # account, minted for any app) would unlock Studio.
            raise jwt.InvalidAudienceError("token not issued for this Studio client")
    except Exception as exc:
        logger.info("OIDC token rejected: %s", exc.__class__.__name__)
        raise AppError(
            type_="https://contractapi.dev/problems/unauthorized",
            title="Unauthorized",
            status=401,
            detail="Invalid or expired OIDC token.",
        ) from exc

    allow = {e.strip().lower() for e in s.studio_oidc_email_allowlist.split(",") if e.strip()}
    if allow:
        email = (claims.get("email") or claims.get("preferred_username") or "").lower()
        if email not in allow:
            raise AppError(
                type_="https://contractapi.dev/problems/forbidden",
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
