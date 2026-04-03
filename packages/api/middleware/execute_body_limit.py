"""ASGI middleware for execute-surface request body limits.

Protects the high-risk execute endpoints before oversized request bodies are fully
materialized in route handlers or Pydantic parsing.
"""

from __future__ import annotations

import json
import re
import uuid

from cors import build_cors_headers
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_BODY_LIMITED_PATHS = (
    re.compile(r"^/v1/capabilities/[^/]+/execute$"),
    re.compile(r"^/v2/capabilities/[^/]+/execute$"),
    re.compile(r"^/v2/providers/[^/]+/execute$"),
    re.compile(r"^/v2/recipes/[^/]+/execute$"),
)


class _BodyTooLarge(Exception):
    """Raised when a request body exceeds the configured size cap."""


class ExecuteBodyLimitMiddleware:
    """Reject oversized execute requests before route parsing.

    This middleware checks both declared Content-Length and streamed request-body
    chunks so callers cannot bypass the limit by omitting or lying about the
    header.
    """

    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    def _should_enforce(self, scope: Scope) -> bool:
        if scope.get("type") != "http":
            return False
        if scope.get("method") != "POST":
            return False
        path = scope.get("path", "")
        return any(pattern.match(path) for pattern in _BODY_LIMITED_PATHS)

    @staticmethod
    def _decode_headers(scope: Scope) -> dict[str, str]:
        return {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }

    async def _send_too_large(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        request_id: str,
        origin: str | None,
    ) -> None:
        body = {
            "error": "payload_too_large",
            "detail": (
                f"Execute request body exceeds the maximum allowed size of "
                f"{self.max_body_bytes} bytes."
            ),
            "resolution": (
                "Reduce the inline payload size or move large inputs to a provider-hosted "
                "file/object URL before calling the execute endpoint."
            ),
            "request_id": request_id,
            "status": 413,
            "limit_bytes": self.max_body_bytes,
        }
        response = Response(
            content=json.dumps(body).encode("utf-8"),
            status_code=413,
            media_type="application/json",
            headers={
                "X-Request-ID": request_id,
                **build_cors_headers(origin),
            },
        )
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._should_enforce(scope):
            await self.app(scope, receive, send)
            return

        headers = self._decode_headers(scope)
        request_id = headers.get("x-request-id") or str(uuid.uuid4())
        origin = headers.get("origin")
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_body_bytes:
                    await self._send_too_large(
                        scope,
                        receive,
                        send,
                        request_id=request_id,
                        origin=origin,
                    )
                    return
            except ValueError:
                pass

        seen_bytes = 0

        async def limited_receive() -> Message:
            nonlocal seen_bytes
            message = await receive()
            if message["type"] == "http.request":
                seen_bytes += len(message.get("body", b""))
                if seen_bytes > self.max_body_bytes:
                    raise _BodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLarge:
            await self._send_too_large(
                scope,
                receive,
                send,
                request_id=request_id,
                origin=origin,
            )
