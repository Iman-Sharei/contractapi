"""Opaque cursor pagination helpers (Zalando API guidelines)."""

from __future__ import annotations

import base64
import json
from typing import Any


def encode_cursor(value: Any) -> str:
    payload = json.dumps({"v": value}, default=str, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> Any:
    padding = "=" * (-len(cursor) % 4)
    raw = base64.urlsafe_b64decode(cursor + padding)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict) or "v" not in data:
        raise ValueError("invalid cursor")
    return data["v"]
