"""Map low-level DB errors to Problem Details without leaking driver internals."""

from __future__ import annotations

import re

from sqlalchemy.exc import DataError, SQLAlchemyError

from contractapi.core.errors import AppError


def db_error(exc: SQLAlchemyError) -> AppError:
    if isinstance(exc, DataError):
        # Bad input value for the column type (e.g. ?id=abc on an integer column).
        return AppError(
            type_="https://contractapi.dev/problems/invalid-filter",
            title="Invalid value",
            status=400,
            detail="A query value does not match the column type. Check your filters and params.",
        )
    return AppError(
        type_="https://contractapi.dev/problems/database-error",
        title="Database error",
        status=500,
        detail=exc.__class__.__name__,
    )


_URL_CREDS = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://)[^/@\s]+@")
_PASSWORD_KV = re.compile(r"(password\s*=\s*)\S+", re.IGNORECASE)


def safe_db_message(exc: BaseException) -> str:
    """First line of a DB/driver error for Studio admins, with credentials stripped.

    Keeps actionable text ("password authentication failed for user", "could not
    translate host name") so non-experts can fix their connection settings.
    """
    raw = str(getattr(exc, "orig", None) or exc).strip()
    first = raw.splitlines()[0] if raw else exc.__class__.__name__
    first = _URL_CREDS.sub(r"\1***@", first)
    first = _PASSWORD_KV.sub(r"\1***", first)
    return first[:300]
