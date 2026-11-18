"""Contract rules shared by models: URL path syntax, reserved routes, SELECT-only SQL guard."""

from __future__ import annotations

import re

_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


# URL path segments: lowercase letters, digits, "-" and "_" (e.g. /order-items, /stats/daily).
PATH_RE = re.compile(r"^(/[a-z0-9][a-z0-9_-]*)+$")


# System routes served next to data endpoints. Only clash when api_prefix is empty.
RESERVED_PATH_SEGMENTS = frozenset(
    {"health", "ready", "metrics", "docs", "redoc", "openapi.json", "auth", "jobs", "graphql"}
)


def suggest_path(value: str) -> str:
    """Best-effort valid path from free text (used in error messages)."""
    parts = [re.sub(r"[^a-z0-9_-]+", "-", p.lower()).strip("-_") for p in value.split("/")]
    joined = "/".join(p for p in parts if p)
    return f"/{joined}" if joined else "/items"


_FORBIDDEN_SQL = (
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "truncate",
    "create",
    "grant",
    "revoke",
    "copy",
    "call",
    "execute",
    "into",
)


def _assert_safe_select(sql: str, *, endpoint_name: str) -> None:
    import re

    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise ValueError(f"Endpoint '{endpoint_name}': sql is empty")
    if ";" in cleaned:
        raise ValueError(f"Endpoint '{endpoint_name}': sql must be a single statement")
    lower = cleaned.lower()
    lines = [ln for ln in lower.splitlines() if not ln.strip().startswith("--")]
    compact = " ".join(lines).strip()
    if not compact.startswith("select") and not compact.startswith("with"):
        raise ValueError(f"Endpoint '{endpoint_name}': sql must start with SELECT or WITH")
    for token in _FORBIDDEN_SQL:
        if re.search(rf"\b{re.escape(token)}\b", compact):
            raise ValueError(
                f"Endpoint '{endpoint_name}': sql contains forbidden keyword '{token}'"
            )
