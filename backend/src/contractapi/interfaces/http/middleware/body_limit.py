"""Reject oversized request bodies (OWASP API4 resource consumption)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from contractapi.core.config import get_settings
from contractapi.core.errors import problem_response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        settings = get_settings()
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                length = int(content_length)
            except ValueError:
                return problem_response(
                    type_="https://contractapi.dev/problems/bad-request",
                    title="Bad Request",
                    status=400,
                    detail="Invalid Content-Length header.",
                )
            if length > settings.max_request_body_bytes:
                return problem_response(
                    type_="https://contractapi.dev/problems/payload-too-large",
                    title="Payload Too Large",
                    status=413,
                    detail=f"Body exceeds {settings.max_request_body_bytes} bytes.",
                )
        return await call_next(request)
