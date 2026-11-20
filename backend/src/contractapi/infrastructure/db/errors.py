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
    first = _readable(getattr(exc, "orig", None) or exc) or exc.__class__.__name__
    first = _URL_CREDS.sub(r"\1***@", first)
    first = _PASSWORD_KV.sub(r"\1***", first)
    return first[:300]


def _readable(err: BaseException) -> str:
    """The human part of a driver error, without codes, byte strings or tuple syntax.

    PyMySQL: (2003, "Can't connect to MySQL server on 'db' (…)")
    pymssql: (20009, b'DB-Lib error message 20009, severity 9:\\nUnable to connect: …\\n')
    """
    args = getattr(err, "args", ())
    if len(args) == 1 and isinstance(args[0], tuple):  # pymssql wraps (code, message) in a tuple
        args = args[0]
    if len(args) >= 2 and isinstance(args[0], int):
        msg = args[-1]
        text = msg.decode("utf-8", "replace") if isinstance(msg, bytes) else str(msg)
    else:
        text = str(err)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    useful = [ln for ln in lines if not ln.startswith(("DB-Lib error message", "Net-Lib error"))]
    return (useful or lines or [""])[0]
