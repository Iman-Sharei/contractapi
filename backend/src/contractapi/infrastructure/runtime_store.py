"""Persist active API set across process restarts (shared volume / single-node)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from contractapi.core.config import get_settings
from contractapi.core.logging import get_logger

logger = get_logger("contractapi.runtime")


def _runtime_dir() -> Path:
    root = Path(get_settings().specs_dir) / ".runtime"
    root.mkdir(parents=True, exist_ok=True)
    return root


def active_path() -> Path:
    return _runtime_dir() / "active.json"


def save_active(primary: str | None, specs: dict[str, dict[str, Any]]) -> None:
    path = active_path()
    payload = {"primary": primary, "specs": specs, "version": 1}
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    logger.info("Persisted %s active API(s) → %s", len(specs), path)


def load_active() -> dict[str, Any] | None:
    path = active_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load active runtime state: %s", exc)
        return None


def clear_active() -> None:
    path = active_path()
    if path.exists():
        path.unlink()
