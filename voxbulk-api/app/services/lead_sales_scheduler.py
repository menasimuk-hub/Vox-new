from __future__ import annotations

import asyncio

from app.core.database import get_sessionmaker
from app.core.logging import get_logger
from app.services.lead_sales_service import process_due_lead_sales_tasks

logger = get_logger(__name__)


async def lead_sales_scheduler_loop(stop_event: asyncio.Event) -> None:
    sessionmaker = get_sessionmaker()
    while not stop_event.is_set():
        try:
            with sessionmaker() as db:
                count = process_due_lead_sales_tasks(db)
                if count:
                    logger.info("lead_sales_tasks_started", extra={"count": count})
        except Exception:
            logger.exception("lead_sales_scheduler_tick_failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            continue
