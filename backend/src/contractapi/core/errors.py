"""RFC 9457 Problem Details for HTTP APIs.

Reference: https://www.rfc-editor.org/rfc/rfc9457.html
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Domain/application error mapped to a Problem Details response."""

    def __init__(
        self,
        *,
        type_: str,
        title: str,
        status: int,
        detail: str | None = None,
        extensions: dict[str, Any] | None = None,
    ) -> None:
        self.type = type_
        self.title = title
        self.status = status
        self.detail = detail
        self.extensions = extensions or {}
        super().__init__(detail or title)


def problem_response(
    *,
    type_: str,
    title: str,
    status: int,
    detail: str | None = None,
    instance: str | None = None,
    extensions: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": type_,
        "title": title,
        "status": status,
    }
    if detail is not None:
        body["detail"] = detail
    if instance is not None:
        body["instance"] = instance
    if extensions:
        body.update(extensions)
    return JSONResponse(
        status_code=status,
        content=body,
        media_type="application/problem+json",
    )


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return problem_response(
        type_=exc.type,
        title=exc.title,
        status=exc.status,
        detail=exc.detail,
        extensions=exc.extensions,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict):
        return problem_response(
            type_=str(detail.get("type", "about:blank")),
            title=str(detail.get("title", exc.status_code)),
            status=exc.status_code,
            detail=detail.get("detail"),
            instance=str(request.url.path),
            extensions={k: v for k, v in detail.items() if k not in {"type", "title", "detail", "status"}},
        )
    return problem_response(
        type_="about:blank",
        title=_status_title(exc.status_code),
        status=exc.status_code,
        detail=str(detail) if detail else None,
        instance=str(request.url.path),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return problem_response(
        type_="https://contractapi.dev/problems/validation-error",
        title="Validation failed",
        status=422,
        detail="One or more request fields are invalid.",
        instance=str(request.url.path),
        extensions={"errors": exc.errors()},
    )


def _status_title(code: int) -> str:
    return {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        409: "Conflict",
        413: "Payload Too Large",
        429: "Too Many Requests",
        500: "Internal Server Error",
    }.get(code, "Error")
