"""Managed data-plane API keys (create / list / revoke) persisted as JSON."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from contractapi.core.config import get_settings

_lock = Lock()


@dataclass
class ApiKeyRecord:
    id: str
    name: str
    prefix: str
    hash: str
    scopes: list[str]
    created_at: float
    revoked_at: float | None = None


def _path() -> Path:
    settings = get_settings()
    root = Path(settings.specs_dir).expanduser().resolve().parent / "api_keys.json"
    root.parent.mkdir(parents=True, exist_ok=True)
    return root


def _load() -> list[ApiKeyRecord]:
    path = _path()
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [ApiKeyRecord(**row) for row in raw]


def _save(rows: list[ApiKeyRecord]) -> None:
    _path().write_text(
        json.dumps([asdict(r) for r in rows], indent=2),
        encoding="utf-8",
    )


def _hash(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def create_key(*, name: str, scopes: list[str] | None = None) -> dict[str, Any]:
    raw = "dk_" + secrets.token_urlsafe(24)
    rec = ApiKeyRecord(
        id=secrets.token_hex(8),
        name=name,
        prefix=raw[:10],
        hash=_hash(raw),
        scopes=scopes or ["*"],
        created_at=time.time(),
    )
    with _lock:
        rows = _load()
        rows.append(rec)
        _save(rows)
    return {"id": rec.id, "name": rec.name, "key": raw, "prefix": rec.prefix, "scopes": rec.scopes}


def list_keys() -> list[dict[str, Any]]:
    with _lock:
        rows = _load()
    return [
        {
            "id": r.id,
            "name": r.name,
            "prefix": r.prefix,
            "scopes": r.scopes,
            "created_at": r.created_at,
            "revoked": r.revoked_at is not None,
        }
        for r in rows
    ]


def revoke_key(key_id: str) -> bool:
    with _lock:
        rows = _load()
        found = False
        for r in rows:
            if r.id == key_id and r.revoked_at is None:
                r.revoked_at = time.time()
                found = True
        if found:
            _save(rows)
        return found


def active_key_set() -> set[str]:
    """Return raw keys cannot be recovered — validate by hash against provided header.

    For runtime we keep hashes and check incoming keys against them, plus env DATA_API_KEYS.
    """
    return set()


def key_is_valid(provided: str) -> bool:
    digest = _hash(provided)
    with _lock:
        for r in _load():
            if r.revoked_at is None and r.hash == digest:
                return True
    return False
