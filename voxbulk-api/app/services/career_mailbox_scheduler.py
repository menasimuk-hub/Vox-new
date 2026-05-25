"""Poll career mailbox on configured interval."""

from __future__ import annotations

import asyncio
import logging

from app.core.database import get_sessionmaker
from app.services.career_mailbox_settings_service import CareerMailboxSettingsService
from app.services.career_mailbox_sync_service import sync_career_mailbox

logger = logging.getLogger(__name__)


async def career_mailbox_scheduler_loop(stop_event: asyncio.Event) -> None:
    tick = 0
    while not stop_event.is_set():
        try:
            await asyncio.sleep(60)
            tick += 1
            with get_sessionmaker()() as db:
                row = CareerMailboxSettingsService.get_row(db)
                interval = max(1, int(row.sync_interval_minutes or 15))
                if not row.is_enabled:
                    continue
                if tick % interval != 0:
                    continue
                sync_career_mailbox(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("career_mailbox_scheduler_tick_failed")
