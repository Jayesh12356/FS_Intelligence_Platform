"""Unified HTTP error envelope + global exception handlers."""

from __future__ import annotations

import logging
import traceback
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.middleware import request_id_var

logger = logging.getLogger(__name__)


def _envelope(
    *,
    error: str,
    code: str,
    status_code: int,
    detail: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "error": error,
        "code": code,
        "status_code": status_code,
        "request_id": request_id_var.get(),
    }
    if detail is not None:
        body["detail"] = detail
    return JSONResponse(status_code=status_code, content=body, headers=headers)


class AppError(Exception):
    """Base application error — subclass for domain-specific failures."""

    code = "app_error"
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class NotFound(AppError):
    code = "not_found"
    status_code = status.HTTP_404_NOT_FOUND


class BadRequest(AppError):
    code = "bad_request"
    status_code = status.HTTP_400_BAD_REQUEST


class Conflict(AppError):
    code = "conflict"
    status_code = status.HTTP_409_CONFLICT


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_req: Request, exc: AppError):
        return _envelope(error=str(exc), code=exc.code, status_code=exc.status_code)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(req: Request, exc: StarletteHTTPException):
        extra_headers: dict[str, str] | None = None
        # RFC 9110 §15.5.6: a 405 response MUST include an Allow header
        # listing the methods the resource supports. Walk the app's
        # router to compute it rather than hard-coding a list.
        if exc.status_code == 405:
            try:
                path = req.url.path
                allowed: set[str] = set()
                for route in app.routes:
                    route_path = getattr(route, "path", None)
                    if route_path == path:
                        methods = getattr(route, "methods", None) or set()
                        allowed.update(methods)
                if allowed:
                    # Drop HEAD duplicates of GET — Allow should be
                    # canonical and not list HEAD separately.
                    extra_headers = {"Allow": ", ".join(sorted(allowed))}
            except Exception:  # pragma: no cover — never fail error handling
                extra_headers = None
        # StarletteHTTPException allows response-wide headers on the exc.
        if not extra_headers and getattr(exc, "headers", None):
            extra_headers = dict(exc.headers)
        return _envelope(
            error=exc.detail if isinstance(exc.detail, str) else "HTTP error",
            code=f"http_{exc.status_code}",
            status_code=exc.status_code,
            detail=exc.detail if not isinstance(exc.detail, str) else None,
            headers=extra_headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_req: Request, exc: RequestValidationError):
        return _envelope(
            error="Request validation failed",
            code="validation_error",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        )

    # Surface LLM-provider failures with a helpful status. Under the
    # paste-per-action model the UI never calls the pipeline for
    # ``provider=cursor`` — it talks to ``/api/cursor-tasks`` instead —
    # so an LLMError here means a real upstream failure (Claude Code
    # CLI missing, Direct API 5xx, etc). Everything becomes a plain
    # 502 ``llm_error`` so the frontend shows one consistent toast.
    try:
        from app.llm.client import LLMError
    except Exception:  # noqa: BLE001 - optional during partial builds
        LLMError = None  # type: ignore[assignment]

    if LLMError is not None:

        @app.exception_handler(LLMError)
        async def _llm_error(_req: Request, exc: LLMError):  # noqa: ANN001
            msg = str(exc) or "LLM call failed"
            provider = getattr(exc, "provider", "") or ""
            code = (
                "claude_cli_unavailable"
                if provider == "claude_code"
                and ("cli" in msg.lower() or "not found" in msg.lower() or "not available" in msg.lower())
                else "llm_error"
            )
            status_code = (
                status.HTTP_503_SERVICE_UNAVAILABLE if code == "claude_cli_unavailable" else status.HTTP_502_BAD_GATEWAY
            )
            return _envelope(
                error=msg,
                code=code,
                status_code=status_code,
                detail={
                    "provider": provider,
                    "model": getattr(exc, "model", "") or "",
                },
            )

    @app.exception_handler(Exception)
    async def _unhandled(_req: Request, exc: Exception):
        logger.error("Unhandled exception: %s\n%s", exc, traceback.format_exc())
        return _envelope(
            error="Internal server error",
            code="internal_error",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
