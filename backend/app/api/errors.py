from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Application-level error that maps to an HTTP error response."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        detail: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Handle :class:`AppError` and return the standard error envelope."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "detail": exc.detail}},
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unhandled exceptions — returns HTTP 500."""
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred.",
                "detail": None,
            }
        },
    )
