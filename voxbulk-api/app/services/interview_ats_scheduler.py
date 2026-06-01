"""Background loop for pending interview ATS scores."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_LOOP_INTERVAL_SEC = 5


async def interview_ats_scheduler_loop(stop_event: asyncio.Event) -> None:
    from app.core.database import get_sessionmaker
    from app.services.interview_ats_service import process_pending_ats_scans

    sessionmaker = get_sessionmaker()
    while not stop_event.is_set():
        try:
            with sessionmaker() as db:
                count = process_pending_ats_scans(db)
                if count:
                    logger.info("interview_ats_processed count=%s", count)
        except Exception:
            logger.exception("interview_ats_scheduler_tick_failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=_LOOP_INTERVAL_SEC)
        except asyncio.TimeoutError:
            pass
