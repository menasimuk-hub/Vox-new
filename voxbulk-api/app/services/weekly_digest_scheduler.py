from __future__ import annotations

import asyncio
from datetime import datetime

from app.core.database import get_sessionmaker
from app.core.logging import get_logger
from app.services.weekly_digest_service import WeeklyDigestService

logger = get_logger(__name__)

_WEEKLY_HOUR_UTC = 8
_WEEKLY_WEEKDAY = 0  # Monday


async def weekly_digest_scheduler_loop(stop_event: asyncio.Event) -> None:
    sessionmaker = get_sessionmaker()
    last_run_key: str | None = None
    while not stop_event.is_set():
        try:
            now = datetime.utcnow()
            run_key = f"{now.isocalendar().year}-W{now.isocalendar().week}"
            if now.weekday() == _WEEKLY_WEEKDAY and now.hour == _WEEKLY_HOUR_UTC and last_run_key != run_key:
                with sessionmaker() as db:
                    count = WeeklyDigestService.send_all_due(db)
                    logger.info("weekly_digest_sent", extra={"count": count, "week": run_key})
                last_run_key = run_key
        except Exception:
            logger.exception("weekly_digest_scheduler_tick_failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=300.0)
        except asyncio.TimeoutError:
            continue
