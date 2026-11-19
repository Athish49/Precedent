import importlib
import pkgutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import AppError, app_error_handler, unhandled_error_handler
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.base import get_session_factory, init_db
from app.services.document_processing.ingest import sweep_stale


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.env)
    init_db(settings.database_url)

    session_factory = get_session_factory()

    # Sweep stale `processing` contracts once at startup (doc_proc task 3.3;
    # plan section 5.1's `sweep_stale`) — catches contracts left behind by a
    # process that died mid-ingest before this startup.
    async with session_factory() as session:
        await sweep_stale(session)

    yield


def create_app() -> FastAPI:
    application = FastAPI(title="Precedent", version="0.1.0", lifespan=lifespan)

    application.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(Exception, unhandled_error_handler)

    # The frontend (Next.js dev server) runs on a different origin
    # (localhost:3000) than this API (localhost:8000), so the browser
    # enforces CORS on every request, starting with an OPTIONS preflight.
    # Never configured anywhere in this app's history; added once this was
    # found to block every frontend call with a 405 on the preflight.
    settings = get_settings()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"]
        if settings.env == "dev"
        else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    routes_path = Path(__file__).parent / "api" / "routes"
    for module_info in pkgutil.iter_modules([str(routes_path)]):
        module = importlib.import_module(f"app.api.routes.{module_info.name}")
        router = getattr(module, "router", None)
        if router is not None:
            application.include_router(router, prefix="/api")

    return application


app = create_app()
