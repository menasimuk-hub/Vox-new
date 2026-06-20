"""Celery tasks for CRM deal-stage survey automation."""

from __future__ import annotations

from app.core.database import get_sessionmaker
from app.core.logging import get_logger
from app.services.crm_deal_survey_automation_service import run_crm_automation_tick
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="crm.poll_deal_survey_automation")
def poll_deal_survey_automation() -> dict:
    with get_sessionmaker()() as db:
        result = run_crm_automation_tick(db)
    logger.info("crm_deal_survey_automation_tick %s", result)
    return result
