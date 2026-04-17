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
) -> JSONResponse:
    body: dict[str, Any] = {
        "error": error,
        "code": code,
        "status_code": status_code,
        "request_id": request_id_var.get(),
    }
    if detail is not None:
        body["detail"] = detail
    return JSONResponse(status_code=status_code, content=body)


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
    async def _http_error(_req: Request, exc: StarletteHTTPException):
        return _envelope(
            error=exc.detail if isinstance(exc.detail, str) else "HTTP error",
            code=f"http_{exc.status_code}",
            status_code=exc.status_code,
            detail=exc.detail if not isinstance(exc.detail, str) else None,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_req: Request, exc: RequestValidationError):
        return _envelope(
            error="Request validation failed",
            code="validation_error",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_req: Request, exc: Exception):
        logger.error("Unhandled exception: %s\n%s", exc, traceback.format_exc())
        return _envelope(
            error="Internal server error",
            code="internal_error",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
