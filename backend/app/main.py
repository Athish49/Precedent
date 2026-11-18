import importlib
import pkgutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api.errors import AppError, app_error_handler, unhandled_error_handler
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.base import get_session_factory, init_db
from app.services.document_processing.clause_types import load_synonym_cache


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.env)
    init_db(settings.database_url)

    # Populate the process-wide clause-type synonym cache once at startup
    # (app/services/document_processing/clause_types.py, task 5.5) so
    # normalize_clause_type() stays a fast synchronous call with no DB
    # round-trip per invocation.
    session_factory = get_session_factory()
    async with session_factory() as session:
        await load_synonym_cache(session)

    yield


def create_app() -> FastAPI:
    application = FastAPI(title="Precedent", version="0.1.0", lifespan=lifespan)

    application.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(Exception, unhandled_error_handler)

    routes_path = Path(__file__).parent / "api" / "routes"
    for module_info in pkgutil.iter_modules([str(routes_path)]):
        module = importlib.import_module(f"app.api.routes.{module_info.name}")
        router = getattr(module, "router", None)
        if router is not None:
            application.include_router(router, prefix="/api")

    return application


app = create_app()
