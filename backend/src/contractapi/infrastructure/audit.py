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
    api: str | None = None,
) -> None:
    settings = get_settings()
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "api": api,
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
    """Newest events last. Read from the log file, so history survives restarts and is the
    same for every server process; the in-memory list is only a fallback."""
    path = Path(get_settings().audit_log_path)
    with _lock:
        if not path.exists():
            return list(_memory[-limit:])
        lines = _tail_lines(path, limit + 1)  # +1: the last line may still be being written
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except ValueError:
            continue  # a half-written last line while another process appends
    return events[-limit:]


def _tail_lines(path: Path, limit: int, block: int = 65_536) -> list[str]:
    """Last `limit` lines without reading the whole (append-only, ever-growing) file."""
    with path.open("rb") as fh:
        fh.seek(0, 2)
        end = fh.tell()
        data = b""
        while end > 0 and data.count(b"\n") <= limit:
            start = max(0, end - block)
            fh.seek(start)
            data = fh.read(end - start) + data
            end = start
    return [ln for ln in data.decode("utf-8", "replace").splitlines() if ln.strip()][-limit:]
