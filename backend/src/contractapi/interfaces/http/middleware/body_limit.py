"""Reject oversized request bodies (OWASP API4 resource consumption).

Pure ASGI: counts the bytes actually received, so chunked requests (no Content-Length)
are limited too — not just honest Content-Length headers.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from contractapi.core.config import get_settings
from contractapi.core.errors import problem_response


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = get_settings().max_request_body_bytes
        too_large = problem_response(
            type_="https://contractapi.dev/problems/payload-too-large",
            title="Payload Too Large",
            status=413,
            detail=f"Body exceeds {limit} bytes.",
        )

        raw_len = dict(scope.get("headers") or []).get(b"content-length")
        if raw_len is not None:
            try:
                declared = int(raw_len)
            except ValueError:
                await problem_response(
                    type_="https://contractapi.dev/problems/bad-request",
                    title="Bad Request",
                    status=400,
                    detail="Invalid Content-Length header.",
                )(scope, receive, send)
                return
            if declared > limit:
                await too_large(scope, receive, send)
                return

        received = 0
        exceeded = False
        started = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            if exceeded:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # Stop reading; the app sees a disconnect and we answer 413 ourselves
                    # (frameworks turn errors raised while reading a body into a generic 400).
                    exceeded = True
                    return {"type": "http.disconnect"}
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if exceeded and not started:
                return  # drop the app's reaction to the cut-off body
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except Exception:
            if not exceeded:
                raise
        if exceeded and not started:
            await too_large(scope, receive, send)
