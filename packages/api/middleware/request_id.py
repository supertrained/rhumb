"""Request ID middleware.

Assigns a unique UUID to every incoming request and exposes it via:
  - request.state.request_id (for use in logging and error handlers)
  - X-Request-ID response header (for client-side correlation)

If the client sends an X-Request-ID header, we echo it back.
Otherwise we generate a fresh UUID4.
"""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Accept client-supplied request ID if present, otherwise generate
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
