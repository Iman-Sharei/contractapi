"""Row-level (BOLA) and soft-delete query helpers."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy import Table, null, true
from sqlalchemy.sql import ColumnElement

from dataapi.core.errors import AppError
from dataapi.domain.models.spec import EndpointSpec


def row_level_clause(
    table: Table,
    endpoint: EndpointSpec,
    request: Request,
) -> ColumnElement[Any] | None:
    cfg = endpoint.row_level
    if not cfg:
        return None
    if cfg.column not in table.c:
        raise AppError(
            type_="https://dataapi.dev/problems/misconfigured",
            title="Misconfigured row-level security",
            status=500,
            detail=f"Column '{cfg.column}' not found on table.",
        )
    principal = getattr(request.state, "principal", {}) or {}
    claims = principal.get("claims") or {}
    value = claims.get(cfg.claim)
    if value is None:
        value = principal.get(cfg.claim)
    if value is None:
        if cfg.required:
            raise AppError(
                type_="https://dataapi.dev/problems/forbidden",
                title="Forbidden",
                status=403,
                detail=f"Missing claim '{cfg.claim}' for row-level access.",
            )
        return true()
    return table.c[cfg.column] == value


def soft_delete_clause(table: Table, endpoint: EndpointSpec) -> ColumnElement[Any] | None:
    cfg = endpoint.soft_delete
    if not cfg:
        return None
    if cfg.column not in table.c:
        raise AppError(
            type_="https://dataapi.dev/problems/misconfigured",
            title="Misconfigured soft delete",
            status=500,
            detail=f"Column '{cfg.column}' not found on table.",
        )
    return table.c[cfg.column].is_(null())


def apply_security_clauses(
    clauses: list[ColumnElement[Any]],
    table: Table,
    endpoint: EndpointSpec,
    request: Request,
) -> list[ColumnElement[Any]]:
    out = list(clauses)
    rl = row_level_clause(table, endpoint, request)
    if rl is not None:
        out.append(rl)
    sd = soft_delete_clause(table, endpoint)
    if sd is not None:
        out.append(sd)
    return out
