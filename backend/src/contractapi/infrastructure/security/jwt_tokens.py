"""JWT issue/verify + refresh/revoke for data-plane auth."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from contractapi.core.config import get_settings
from contractapi.core.errors import AppError
from contractapi.domain.models.spec import JwtConfig
from contractapi.infrastructure.security.token_store import (
    blacklist_access,
    get_refresh,
    is_access_revoked,
    new_jti,
    revoke_refresh,
    store_refresh,
)


def issue_token_pair(
    *,
    subject: str,
    roles: list[str],
    jwt_cfg: JwtConfig,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    _require_secret(settings.jwt_secret)
    now = datetime.now(UTC)
    access_jti = new_jti()
    refresh_jti = new_jti()
    access_ttl = timedelta(minutes=jwt_cfg.access_ttl_minutes)
    refresh_ttl = timedelta(days=jwt_cfg.refresh_ttl_days)

    access_payload: dict[str, Any] = {
        "sub": subject,
        "roles": roles,
        "iss": jwt_cfg.issuer,
        "aud": jwt_cfg.audience,
        "iat": now,
        "exp": now + access_ttl,
        "jti": access_jti,
        "typ": "access",
    }
    if extra:
        access_payload.update(extra)

    refresh_payload = {
        "sub": subject,
        "roles": roles,
        "iss": jwt_cfg.issuer,
        "aud": jwt_cfg.audience,
        "iat": now,
        "exp": now + refresh_ttl,
        "jti": refresh_jti,
        "typ": "refresh",
    }
    access = jwt.encode(access_payload, settings.jwt_secret, algorithm=jwt_cfg.algorithm)
    refresh = jwt.encode(refresh_payload, settings.jwt_secret, algorithm=jwt_cfg.algorithm)
    store_refresh(
        refresh_jti,
        {"sub": subject, "roles": roles, "extra": extra or {}},
        ttl_seconds=int(refresh_ttl.total_seconds()),
    )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": int(access_ttl.total_seconds()),
    }


def issue_token(
    *,
    subject: str,
    roles: list[str],
    jwt_cfg: JwtConfig,
    expires_minutes: int = 60,
    extra: dict[str, Any] | None = None,
) -> str:
    """Backward-compatible single access token (no refresh)."""
    pair = issue_token_pair(
        subject=subject,
        roles=roles,
        jwt_cfg=JwtConfig(
            issuer=jwt_cfg.issuer,
            audience=jwt_cfg.audience,
            algorithm=jwt_cfg.algorithm,
            access_ttl_minutes=expires_minutes,
            refresh_ttl_days=jwt_cfg.refresh_ttl_days,
        ),
        extra=extra,
    )
    return pair["access_token"]


def refresh_tokens(refresh_token: str, jwt_cfg: JwtConfig) -> dict[str, Any]:
    claims = verify_token(refresh_token, jwt_cfg, expected_typ="refresh")
    jti = str(claims.get("jti") or "")
    stored = get_refresh(jti)
    if not stored:
        raise AppError(
            type_="https://contractapi.dev/problems/invalid-token",
            title="Invalid refresh token",
            status=401,
            detail="Refresh token is unknown or revoked.",
        )
    revoke_refresh(jti)
    return issue_token_pair(
        subject=str(stored.get("sub") or claims.get("sub")),
        roles=list(stored.get("roles") or claims.get("roles") or []),
        jwt_cfg=jwt_cfg,
        extra=stored.get("extra") if isinstance(stored.get("extra"), dict) else None,
    )


def revoke_token(token: str, jwt_cfg: JwtConfig) -> None:
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[jwt_cfg.algorithm],
            audience=jwt_cfg.audience,
            issuer=jwt_cfg.issuer,
            options={"verify_exp": False},
        )
    except jwt.InvalidTokenError as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/invalid-token",
            title="Invalid token",
            status=401,
            detail="JWT validation failed.",
        ) from exc
    jti = str(claims.get("jti") or "")
    typ = claims.get("typ")
    exp = claims.get("exp")
    ttl = 3600
    if isinstance(exp, (int, float)):
        ttl = max(int(exp - datetime.now(UTC).timestamp()), 60)
    if typ == "refresh":
        revoke_refresh(jti)
    elif jti:
        blacklist_access(jti, ttl)


def verify_token(
    token: str,
    jwt_cfg: JwtConfig,
    *,
    expected_typ: str | None = "access",
) -> dict[str, Any]:
    settings = get_settings()
    _require_secret(settings.jwt_secret)
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[jwt_cfg.algorithm],
            audience=jwt_cfg.audience,
            issuer=jwt_cfg.issuer,
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/token-expired",
            title="Token expired",
            status=401,
            detail="JWT has expired.",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise AppError(
            type_="https://contractapi.dev/problems/invalid-token",
            title="Invalid token",
            status=401,
            detail="JWT validation failed.",
        ) from exc

    if expected_typ and claims.get("typ") not in {expected_typ, None}:
        # allow legacy tokens without typ when expecting access
        if not (expected_typ == "access" and claims.get("typ") is None):
            raise AppError(
                type_="https://contractapi.dev/problems/invalid-token",
                title="Invalid token type",
                status=401,
                detail=f"Expected {expected_typ} token.",
            )
    jti = str(claims.get("jti") or "")
    if jti and expected_typ != "refresh" and is_access_revoked(jti):
        raise AppError(
            type_="https://contractapi.dev/problems/token-revoked",
            title="Token revoked",
            status=401,
            detail="Access token has been revoked.",
        )
    return claims


def extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _require_secret(secret: str) -> None:
    if not secret:
        raise AppError(
            type_="https://contractapi.dev/problems/misconfigured",
            title="JWT not configured",
            status=500,
            detail="Set JWT_SECRET in the environment.",
        )
