"""Refresh-token and revoke (jti blacklist) store."""

from __future__ import annotations

import secrets
from typing import Any

from contractapi.infrastructure.kv import get_kv, kv_json_get, kv_json_set


def store_refresh(jti: str, payload: dict[str, Any], ttl_seconds: int) -> None:
    kv_json_set(f"refresh:{jti}", payload, ttl_seconds)


def get_refresh(jti: str) -> dict[str, Any] | None:
    data = kv_json_get(f"refresh:{jti}")
    return data if isinstance(data, dict) else None


def revoke_refresh(jti: str) -> None:
    get_kv().delete(f"refresh:{jti}")


def blacklist_access(jti: str, ttl_seconds: int) -> None:
    get_kv().set(f"revoke:{jti}", "1", ttl_seconds)


def is_access_revoked(jti: str) -> bool:
    return get_kv().get(f"revoke:{jti}") is not None


def new_jti() -> str:
    return secrets.token_urlsafe(24)
