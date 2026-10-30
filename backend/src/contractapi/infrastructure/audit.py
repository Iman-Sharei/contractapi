"""Append-only audit trail (JSONL)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from contractapi.core.config import get_settings

_lock = Lock()
_memory: list[dict[str, Any]] = []


def audit_event(
    *,
    action: str,
    endpoint: str | None = None,
    resource_id: Any = None,
    principal: dict[str, Any] | None = None,
    status: int | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    settings = get_settings()
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "endpoint": endpoint,
        "resource_id": resource_id,
        "sub": (principal or {}).get("sub"),
        "roles": (principal or {}).get("roles"),
        "status": status,
        "meta": meta or {},
    }
    with _lock:
        _memory.append(event)
        if len(_memory) > 5_000:
            del _memory[:2_000]
        path = Path(settings.audit_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, default=str) + "\n")


def recent_events(limit: int = 100) -> list[dict[str, Any]]:
    with _lock:
        return list(_memory[-limit:])
