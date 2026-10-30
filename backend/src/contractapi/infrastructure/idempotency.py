"""Idempotency-Key store (memory/Redis via KV)."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

from contractapi.infrastructure.kv import get_kv, kv_json_get, kv_json_set


@dataclass
class IdempotentRecord:
    fingerprint: str
    status_code: int
    body: Any
    headers: dict[str, str]
    created_at: float


class IdempotencyStore:
    def __init__(self, *, ttl_seconds: int = 86400) -> None:
        self.ttl_seconds = ttl_seconds

    def get(self, key: str) -> IdempotentRecord | None:
        raw = kv_json_get(f"idem:{key}")
        if not isinstance(raw, dict):
            return None
        return IdempotentRecord(
            fingerprint=str(raw["fingerprint"]),
            status_code=int(raw["status_code"]),
            body=raw.get("body"),
            headers=dict(raw.get("headers") or {}),
            created_at=float(raw.get("created_at") or time.time()),
        )

    def put(self, key: str, record: IdempotentRecord) -> None:
        kv_json_set(
            f"idem:{key}",
            {
                "fingerprint": record.fingerprint,
                "status_code": record.status_code,
                "body": record.body,
                "headers": record.headers,
                "created_at": record.created_at,
            },
            self.ttl_seconds,
        )

    def clear(self) -> None:
        get_kv().delete_prefix("idem:")


def fingerprint_payload(method: str, path: str, body: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(method.upper().encode())
    digest.update(b"|")
    digest.update(path.encode())
    digest.update(b"|")
    digest.update(body)
    return digest.hexdigest()


def make_scope_key(scope: str, idem_key: str) -> str:
    return f"{scope}:{idem_key}"


idempotency_store = IdempotencyStore()


def serialize_json_body(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
