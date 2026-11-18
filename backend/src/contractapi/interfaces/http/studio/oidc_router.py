"""Browser OIDC cookie login (Auth.js-style BFF endpoints on the Studio API)."""

from __future__ import annotations

import secrets
import time
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from contractapi.core.config import get_settings
from contractapi.core.errors import AppError
from contractapi.infrastructure.security.oidc import (
    exchange_code_for_tokens,
    oidc_browser_enabled,
    oidc_cookie_name,
    oidc_discovery,
    oidc_enabled,
    pkce_pair,
    verify_studio_oidc_token,
)

router = APIRouter(prefix="/studio/oidc", tags=["studio-oidc"])

_STATE_COOKIE = "contractapi_oidc_state"
_STATE_TTL = 600


def safe_return_to(value: str | None) -> str:
    """Only same-site absolute paths (blocks //evil.com and /\\evil.com open redirects)."""
    v = (value or "").strip()
    if not v.startswith("/") or v.startswith(("//", "/\\")) or "\n" in v or "|" in v:
        return "/studio"
    return v


@router.get("/config")
def oidc_config() -> dict[str, Any]:
    s = get_settings()
    return {
        "enabled": oidc_enabled(s),
        "browser_login": oidc_browser_enabled(s),
        "issuer": s.studio_oidc_issuer.strip() or None,
        "login_path": "/studio/oidc/login",
        "logout_path": "/studio/oidc/logout",
        "me_path": "/studio/oidc/me",
    }


@router.get("/login")
def oidc_login(request: Request, return_to: str = "/studio") -> Response:
    s = get_settings()
    if not oidc_browser_enabled(s):
        raise AppError(
            type_="https://contractapi.dev/problems/misconfigured",
            title="OIDC browser login disabled",
            status=503,
            detail=(
                "Set STUDIO_OIDC_ISSUER, STUDIO_OIDC_CLIENT_ID, and "
                "STUDIO_OIDC_REDIRECT_URI to enable cookie login."
            ),
        )
    meta = oidc_discovery(s.studio_oidc_issuer.strip())
    authorize = meta.get("authorization_endpoint")
    if not authorize:
        raise AppError(
            type_="https://contractapi.dev/problems/misconfigured",
            title="OIDC misconfigured",
            status=500,
            detail="authorization_endpoint missing from discovery document.",
        )
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier, challenge = pkce_pair()
    params = {
        "response_type": "code",
        "client_id": s.studio_oidc_client_id.strip(),
        "redirect_uri": s.studio_oidc_redirect_uri.strip(),
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if s.studio_oidc_audience.strip():
        params["audience"] = s.studio_oidc_audience.strip()
    url = f"{authorize}?{urlencode(params)}"
    resp = RedirectResponse(url=url, status_code=302)
    secure = bool(s.studio_oidc_cookie_secure)
    resp.set_cookie(
        _STATE_COOKIE,
        # httpOnly, short-lived; binds this browser to the login it started (CSRF/replay).
        f"{state}|{safe_return_to(return_to)}|{int(time.time())}|{nonce}|{verifier}",
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=_STATE_TTL,
        path="/",
    )
    return resp


@router.get("/callback")
def oidc_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    s = get_settings()
    if error:
        raise AppError(
            type_="https://contractapi.dev/problems/unauthorized",
            title="OIDC error",
            status=401,
            detail=error,
        )
    if not code or not state:
        raise AppError(
            type_="https://contractapi.dev/problems/unauthorized",
            title="Unauthorized",
            status=401,
            detail="Missing code/state from IdP callback.",
        )
    raw_state = request.cookies.get(_STATE_COOKIE) or ""
    parts = raw_state.split("|")
    if len(parts) != 5 or not secrets.compare_digest(parts[0], state):
        raise AppError(
            type_="https://contractapi.dev/problems/unauthorized",
            title="Unauthorized",
            status=401,
            detail="Invalid OIDC state. Please sign in again.",
        )
    _, return_to, issued, nonce, verifier = parts
    try:
        if int(issued) + _STATE_TTL < time.time():
            raise ValueError("expired")
    except ValueError as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/unauthorized",
            title="Unauthorized",
            status=401,
            detail="OIDC login took too long. Please sign in again.",
        ) from exc
    return_to = safe_return_to(return_to)

    tokens = exchange_code_for_tokens(code, s, code_verifier=verifier)
    id_token = tokens.get("id_token")
    if not id_token:
        raise AppError(
            type_="https://contractapi.dev/problems/unauthorized",
            title="Unauthorized",
            status=401,
            detail="The identity provider did not return an id_token.",
        )
    # id_token proves this login: issued for our client_id and carrying the nonce we sent.
    id_claims = verify_studio_oidc_token(str(id_token), s)["claims"]
    if not secrets.compare_digest(str(id_claims.get("nonce") or ""), nonce):
        raise AppError(
            type_="https://contractapi.dev/problems/unauthorized",
            title="Unauthorized",
            status=401,
            detail="OIDC nonce mismatch. Please sign in again.",
        )
    # Cookie value must pass the same check every Studio request applies.
    access = tokens.get("access_token") or id_token
    try:
        verify_studio_oidc_token(str(access), s)
    except AppError:
        access = id_token

    # Prefer frontend origin redirect when configured
    base = (s.studio_oidc_post_login_url or "").strip().rstrip("/")
    location = f"{base}{return_to}" if base else return_to
    resp = RedirectResponse(url=location, status_code=302)
    secure = bool(s.studio_oidc_cookie_secure)
    max_age = int(tokens.get("expires_in") or 3600)
    resp.set_cookie(
        oidc_cookie_name(s),
        str(access),
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=max_age,
        path="/",
    )
    resp.delete_cookie(_STATE_COOKIE, path="/")
    return resp


@router.post("/logout")
@router.get("/logout")
def oidc_logout() -> Response:
    s = get_settings()
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(oidc_cookie_name(s), path="/")
    resp.delete_cookie(_STATE_COOKIE, path="/")
    return resp


@router.get("/me")
def oidc_me(request: Request) -> dict[str, Any]:
    s = get_settings()
    token = request.cookies.get(oidc_cookie_name(s))
    if not token:
        return {"authenticated": False, "browser_login": oidc_browser_enabled(s)}
    try:
        principal = verify_studio_oidc_token(token, s)
    except AppError:
        return {"authenticated": False, "browser_login": oidc_browser_enabled(s)}
    return {
        "authenticated": True,
        "sub": principal.get("sub"),
        "email": principal.get("email"),
        "roles": principal.get("roles") or [],
        "auth_mode": "oidc_cookie",
    }
