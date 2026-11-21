"""Map low-level DB errors to Problem Details without leaking driver internals."""

from __future__ import annotations

import re

from sqlalchemy.exc import DataError, SQLAlchemyError

from contractapi.core.errors import AppError

SCHEMA_CHANGED = "https://contractapi.dev/problems/schema-changed"
SCHEMA_CHANGED_DETAIL = (
    "The database no longer matches this API: a column or table it uses was renamed or "
    "removed. In Studio, open this API and use 'Check database changes', then update or "
    "remove the affected fields and make the API live again."
)
# Postgres, MySQL, SQL Server, DuckDB, SQLite, Snowflake, BigQuery wording for a missing
# column/table. Matched on the driver message, which is never shown to clients.
_MISSING_OBJECT = re.compile(
    r"column .* does not exist|relation .* does not exist|unknown column|table '.*' doesn't exist"
    r"|invalid column name|invalid object name|no such (column|table)"
    r"|referenced column .* not found|table with name .* does not exist|invalid identifier"
    r"|unrecognized name|not found: table",
    re.IGNORECASE,
)


MISSING_VALUE_DETAIL = (
    "A required value is missing: the database needs a value for a column that was not sent. "
    "Send every required field, or give the column a default value in Studio."
)
_MISSING_VALUE = re.compile(
    r"violates not-null constraint|doesn't have a default value|cannot be null"
    r"|cannot insert the value null|not null constraint failed",
    re.IGNORECASE,
)


def is_missing_value(exc: BaseException) -> bool:
    """NOT NULL column left empty (IntegrityError on most drivers, OperationalError on MySQL)."""
    return bool(_MISSING_VALUE.search(_readable(getattr(exc, "orig", None) or exc)))


def missing_value_error() -> AppError:
    return AppError(
        type_="https://contractapi.dev/problems/validation-error",
        title="Validation failed",
        status=422,
        detail=MISSING_VALUE_DETAIL,
    )


def is_schema_change(exc: BaseException) -> bool:
    return bool(_MISSING_OBJECT.search(_readable(getattr(exc, "orig", None) or exc)))


def db_error(exc: SQLAlchemyError) -> AppError:
    if is_schema_change(exc):
        return AppError(
            type_=SCHEMA_CHANGED,
            title="Database changed",
            status=409,
            detail=SCHEMA_CHANGED_DETAIL,
        )
    if is_missing_value(exc):
        return missing_value_error()
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
