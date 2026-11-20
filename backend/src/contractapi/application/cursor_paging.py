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


def check_cursor_sort(sort: str | None, primary_key: str) -> None:
    """Next-page links always return rows in primary-key order. Refuse another ?sort=
    instead of silently ignoring it (the caller would trust an order that isn't applied)."""
    if sort and sort != primary_key:
        from contractapi.core.errors import AppError

        raise AppError(
            type_="https://contractapi.dev/problems/invalid-sort",
            title="Sort field not allowed",
            status=400,
            detail=(
                f"This endpoint uses next-page links, which always return rows in "
                f"'{primary_key}' order. Remove ?sort=, or switch the endpoint's paging to "
                f"page numbers to sort by other fields."
            ),
            extensions={"allowed": [primary_key], "rejected": sort},
        )
