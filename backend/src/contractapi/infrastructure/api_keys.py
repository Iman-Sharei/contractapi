"""Managed data-plane API keys, persisted as JSON next to the specs (hashes only).

A key opens a list of APIs (or "*" = all) with "read" (GET only) or "write" access, can expire,
and remembers when it was last used. Keys created before scopes existed keep working on every
API ("*"); a legacy key whose scopes were only "read" is read-only, as its creator asked.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from threading import Lock
from typing import Any

from contractapi.core.config import get_settings

_lock = Lock()
_cache: tuple[tuple[int, int], list[ApiKeyRecord]] | None = None
_touched: dict[str, float] = {}
TOUCH_EVERY_SECONDS = 60  # "last used" is kept to the minute: no file write on every request
ALL_APIS = "*"


@dataclass
class ApiKeyRecord:
    id: str
    name: str
    prefix: str
    hash: str
    scopes: list[str]  # legacy; kept so files written by older versions still load
    created_at: float
    revoked_at: float | None = None
    apis: list[str] = field(default_factory=lambda: [ALL_APIS])
    access: str = "write"
    expires_at: float | None = None
    last_used_at: float | None = None

    def allows(self, api: str | None) -> bool:
        return ALL_APIS in self.apis or (api is not None and api in self.apis)

    def expired(self, now: float | None = None) -> bool:
        return self.expires_at is not None and self.expires_at <= (now or time.time())


def _from_row(row: dict[str, Any]) -> ApiKeyRecord:
    row = dict(row)
    if "access" not in row:  # written before scopes were enforced
        scopes = set(row.get("scopes") or [ALL_APIS])
        row["access"] = "read" if scopes and scopes <= {"read"} else "write"
    known = {f.name for f in fields(ApiKeyRecord)}
    return ApiKeyRecord(**{k: v for k, v in row.items() if k in known})


def _path() -> Path:
    settings = get_settings()
    root = Path(settings.specs_dir).expanduser().resolve().parent / "api_keys.json"
    root.parent.mkdir(parents=True, exist_ok=True)
    return root


def _load() -> list[ApiKeyRecord]:
    """All keys; re-read only when the file changed (another process may have written it)."""
    global _cache
    path = _path()
    try:
        stat = path.stat()
    except FileNotFoundError:
        return []
    signature = (stat.st_mtime_ns, stat.st_size)
    if _cache is not None and _cache[0] == signature:
        return _cache[1]
    rows = [_from_row(r) for r in json.loads(path.read_text(encoding="utf-8"))]
    _cache = (signature, rows)
    return rows


def _save(rows: list[ApiKeyRecord]) -> None:
    global _cache
    path = _path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps([asdict(r) for r in rows], indent=2), encoding="utf-8")
    os.replace(tmp, path)  # readers never see a half-written file
    _cache = None


def _hash(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def create_key(
    *,
    name: str,
    apis: list[str] | None = None,
    access: str | None = None,
    expires_at: float | None = None,
    scopes: list[str] | None = None,
) -> dict[str, Any]:
    """New key; the raw value is returned once and only its hash is stored."""
    if access is None:  # older callers only sent scopes
        access = "read" if scopes and set(scopes) <= {"read"} else ("write" if scopes else "read")
    raw = "dk_" + secrets.token_urlsafe(24)
    rec = ApiKeyRecord(
        id=secrets.token_hex(8),
        name=name,
        prefix=raw[:10],
        hash=_hash(raw),
        scopes=scopes or [],
        created_at=time.time(),
        apis=sorted(set(apis or [ALL_APIS])),
        access=access,
        expires_at=expires_at,
    )
    with _lock:
        rows = list(_load())
        rows.append(rec)
        _save(rows)
    return {**_public(rec), "key": raw}


def _public(r: ApiKeyRecord) -> dict[str, Any]:
    return {
        "id": r.id,
        "name": r.name,
        "prefix": r.prefix,
        "apis": r.apis,
        "access": r.access,
        "scopes": r.scopes,
        "created_at": r.created_at,
        "expires_at": r.expires_at,
        "last_used_at": r.last_used_at,
        "revoked": r.revoked_at is not None,
        "expired": r.expired(),
    }


def list_keys() -> list[dict[str, Any]]:
    with _lock:
        return [_public(r) for r in _load()]


def has_active_keys() -> bool:
    """Any key that is not revoked (an expired one too: its caller must hear it expired)."""
    with _lock:
        return any(r.revoked_at is None for r in _load())


def revoke_key(key_id: str) -> bool:
    with _lock:
        rows = list(_load())
        found = False
        for r in rows:
            if r.id == key_id and r.revoked_at is None:
                r.revoked_at = time.time()
                found = True
        if found:
            _save(rows)
        return found


def find_key(provided: str) -> ApiKeyRecord | None:
    """The stored, not revoked key with this value (expiry and scope are checked by callers)."""
    digest = _hash(provided)
    with _lock:
        for r in _load():
            if r.revoked_at is None and secrets.compare_digest(r.hash, digest):
                return r
    return None


def key_is_valid(provided: str) -> bool:
    rec = find_key(provided)
    return rec is not None and not rec.expired()


def touch(rec: ApiKeyRecord) -> None:
    """Record use, at most once a minute per key and process."""
    now = time.time()
    if now - _touched.get(rec.id, 0) < TOUCH_EVERY_SECONDS:
        return
    _touched[rec.id] = now
    with _lock:
        rows = list(_load())
        for r in rows:
            if r.id == rec.id:
                r.last_used_at = now
        _save(rows)


def active_key_set() -> set[str]:
    """Raw keys cannot be recovered (only hashes are stored); kept for older imports."""
    return set()
