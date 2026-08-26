from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    db: bool
    embedding_model: bool
    storage: bool


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    db_ok = False
    embedding_ok = False
    storage_ok = False

    try:
        from app.db.base import get_session_factory
        async with get_session_factory()() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        pass

    try:
        from app.core.embeddings import embed
        await embed(["health"])
        embedding_ok = True
    except Exception:
        pass

    try:
        from app.core.config import get_settings
        from app.core.storage import get_storage
        storage = get_storage(get_settings())
        storage.put("__health_check__", b"ok")
        storage.get("__health_check__")
        storage_ok = True
    except Exception:
        pass

    return HealthResponse(
        status="ok",
        db=db_ok,
        embedding_model=embedding_ok,
        storage=storage_ok,
    )
