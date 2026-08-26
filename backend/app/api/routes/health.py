from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    db: bool


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    db_ok = False
    try:
        from app.db.base import get_session_factory

        async with get_session_factory()() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        pass
    return HealthResponse(status="ok", db=db_ok)
