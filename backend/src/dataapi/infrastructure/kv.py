"""Key-value store: in-memory by default, Redis when REDIS_URL is set."""

from __future__ import annotations

import json
import time
from threading import Lock
from typing import Any, Protocol

from dataapi.core.config import get_settings
from dataapi.core.logging import get_logger

logger = get_logger("dataapi.kv")


class KvStore(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, ttl_seconds: int) -> None: ...
    def delete(self, key: str) -> None: ...
    def delete_prefix(self, prefix: str) -> int: ...


class MemoryKv:
    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float]] = {}
        self._lock = Lock()

    def get(self, key: str) -> str | None:
        now = time.monotonic()
        with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            value, expires = item
            if expires < now:
                del self._data[key]
                return None
            return value

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        with self._lock:
            self._data[key] = (value, time.monotonic() + max(ttl_seconds, 1))

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def delete_prefix(self, prefix: str) -> int:
        with self._lock:
            keys = [k for k in self._data if k.startswith(prefix)]
            for k in keys:
                del self._data[k]
            return len(keys)


class RedisKv:
    def __init__(self, url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(url, decode_responses=True)

    def get(self, key: str) -> str | None:
        return self._client.get(key)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._client.setex(key, max(ttl_seconds, 1), value)

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def delete_prefix(self, prefix: str) -> int:
        keys = list(self._client.scan_iter(match=f"{prefix}*"))
        if keys:
            return int(self._client.delete(*keys))
        return 0


_store: KvStore | None = None


def get_kv() -> KvStore:
    global _store
    if _store is not None:
        return _store
    settings = get_settings()
    if settings.redis_url:
        try:
            _store = RedisKv(settings.redis_url)
            logger.info("Using Redis KV at %s", settings.redis_url.split("@")[-1])
            return _store
        except Exception as exc:
            logger.warning("Redis unavailable (%s); falling back to memory KV", exc)
    _store = MemoryKv()
    return _store


def reset_kv() -> None:
    global _store
    _store = None


def kv_json_get(key: str) -> Any | None:
    raw = get_kv().get(key)
    if raw is None:
        return None
    return json.loads(raw)


def kv_json_set(key: str, value: Any, ttl_seconds: int) -> None:
    get_kv().set(key, json.dumps(value, default=str), ttl_seconds)
