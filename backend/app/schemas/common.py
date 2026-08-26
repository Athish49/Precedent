from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Detail portion of an error envelope."""

    code: str
    message: str
    detail: Any = None


class ErrorEnvelope(BaseModel):
    """Standard error response envelope."""

    error: ErrorDetail


class PaginationParams(BaseModel):
    """Common pagination query parameters."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)


class PaginatedResponse[T](BaseModel):
    """Generic paginated list response."""

    items: list[T]
    total: int
    page: int
    page_size: int
