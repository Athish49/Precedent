#!/usr/bin/env python3
"""Cron entrypoint: run one daily monitor pass.

Usage: python scripts/run_monitor.py
"""
from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.base import get_session_factory, init_db
from app.services.obligations.monitor import run_monitor


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.env)
    init_db(settings.database_url)
    factory = get_session_factory()
    async with factory() as session:
        result = await run_monitor(session)
        await session.commit()
    logging.getLogger(__name__).info(
        "Monitor pass complete: %d deadline alerts, %d renewal alerts",
        len(result.deadline_alerts),
        len(result.renewal_alerts),
    )


if __name__ == "__main__":
    asyncio.run(main())
