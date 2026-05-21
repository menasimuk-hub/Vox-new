from __future__ import annotations

import logging

from app.core.database import get_sessionmaker
from app.services.usage_wallet_service import UsageWalletService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="billing.rollover_usage_periods")
def rollover_usage_periods_task() -> dict:
    with get_sessionmaker()() as db:
        stats = UsageWalletService.rollover_due_periods(db)
    logger.info("usage_period_rollover_complete", extra=stats)
    return stats
