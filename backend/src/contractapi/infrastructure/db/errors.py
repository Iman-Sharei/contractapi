"""Map low-level DB errors to Problem Details without leaking driver internals."""

from __future__ import annotations

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
