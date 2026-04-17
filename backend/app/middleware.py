"""Request ID + access log middleware."""

from __future__ import annotations

import contextvars
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
logger = logging.getLogger("app.access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach an X-Request-ID (fresh or propagated), log method/path/status/latency."""

    HEADER = "X-Request-ID"

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get(self.HEADER) or uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        request.state.request_id = rid
        start = time.perf_counter()
        status_code = 500
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            response.headers[self.HEADER] = rid
            return response
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "%s %s -> %d (%.1fms) rid=%s",
                request.method,
                request.url.path,
                status_code,
                elapsed_ms,
                rid,
            )
            request_id_var.reset(token)


class RequestIdLogFilter(logging.Filter):
    """Inject request_id into LogRecord for formatters that want it."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.request_id = request_id_var.get()
        except Exception:
            record.request_id = "-"
        return True
