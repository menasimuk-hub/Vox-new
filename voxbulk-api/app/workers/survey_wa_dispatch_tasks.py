"""Celery tasks for WhatsApp survey dispatch retries."""

from __future__ import annotations

from app.core.database import get_sessionmaker
from app.core.logging import get_logger
from app.services.survey_dispatch_service import SurveyDispatchService
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="survey.retry_deferred_wa_starts")
def retry_deferred_wa_starts(*, limit: int = 50) -> dict:
    with get_sessionmaker()() as db:
        result = SurveyDispatchService.retry_deferred_wa_starts(db, limit=limit)
    logger.info(
        "survey_retry_deferred_wa_starts attempted=%s sent=%s still_deferred=%s skipped=%s",
        result.get("attempted"),
        result.get("sent"),
        result.get("still_deferred"),
        result.get("skipped"),
    )
    return result
