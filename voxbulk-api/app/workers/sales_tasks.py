from __future__ import annotations

import logging

from app.core.database import get_sessionmaker
from app.services.sales_automation_service import SalesAutomationService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="sales.process_promo_followups")
def process_promo_followups_task() -> dict:
    with get_sessionmaker()() as db:
        stats = SalesAutomationService.process_due_followups(db)
    logger.info("sales_promo_followups_complete", extra=stats)
    return stats
