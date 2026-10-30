"""Sensitive-column policy (security by omission).

OWASP API3:2023 Broken Object Property Level Authorization —
never expose fields the consumer did not explicitly allow.
"""

from __future__ import annotations

import re

SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"password", re.I),
    re.compile(r"passwd", re.I),
    re.compile(r"secret", re.I),
    re.compile(r"token", re.I),
    re.compile(r"api[_-]?key", re.I),
    re.compile(r"private[_-]?key", re.I),
    re.compile(r"ssn", re.I),
    re.compile(r"credit[_-]?card", re.I),
    re.compile(r"cvv", re.I),
    re.compile(r"salt", re.I),
    re.compile(r"hash$", re.I),
)

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def is_sensitive_column(name: str) -> bool:
    return any(pattern.search(name) for pattern in SENSITIVE_PATTERNS)


def find_sensitive_columns(columns: list[str]) -> list[str]:
    return [col for col in columns if is_sensitive_column(col)]


def assert_fields_safe(fields: list[str], *, allow_sensitive: bool = False) -> None:
    if allow_sensitive:
        return
    blocked = find_sensitive_columns(fields)
    if blocked:
        raise ValueError(
            "Refusing to expose sensitive columns without allow_sensitive=true: "
            + ", ".join(blocked)
        )
