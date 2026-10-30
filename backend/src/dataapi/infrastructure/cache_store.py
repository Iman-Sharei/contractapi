"""TTL response cache backed by KV (memory or Redis)."""

from __future__ import annotations

from typing import Any

from dataapi.infrastructure.kv import get_kv, kv_json_get, kv_json_set


class ResponseCache:
    def get(self, key: str) -> Any | None:
        return kv_json_get(f"cache:{key}")

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        kv_json_set(f"cache:{key}", value, ttl_seconds)

    def invalidate_prefix(self, prefix: str) -> int:
        return get_kv().delete_prefix(f"cache:{prefix}")

    def clear(self) -> None:
        get_kv().delete_prefix("cache:")


response_cache = ResponseCache()
