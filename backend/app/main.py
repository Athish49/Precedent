import importlib
import pkgutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api.errors import AppError, app_error_handler, unhandled_error_handler
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.base import init_db


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.env)
    init_db(settings.database_url)
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
