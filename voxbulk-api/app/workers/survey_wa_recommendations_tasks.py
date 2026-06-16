"""Celery tasks for async survey AI recommendations."""

from __future__ import annotations

from app.core.database import get_sessionmaker
from app.core.logging import get_logger
from app.models.service_order import ServiceOrder
from app.services.survey_results_service import generate_and_store_action_recommendations
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


def enqueue_survey_recommendations(order_id: str) -> None:
    """Queue AI recommendations generation; no-op if Celery unavailable."""
    try:
        generate_survey_recommendations_task.delay(order_id=order_id)
    except Exception:
        logger.exception("survey_recommendations_enqueue_failed order_id=%s", order_id)


@celery_app.task(name="survey.generate_recommendations", bind=True, max_retries=2, default_retry_delay=30)
def generate_survey_recommendations_task(self, *, order_id: str) -> dict:
    with get_sessionmaker()() as db:
        order = db.get(ServiceOrder, order_id)
        if order is None:
            return {"ok": False, "error": "order_not_found"}
        try:
            result = generate_and_store_action_recommendations(db, order)
            if not result.get("ok") and self.request.retries < self.max_retries:
                raise self.retry(exc=RuntimeError(str(result.get("error") or "recommendations failed")))
            return result
        except Exception as exc:
            logger.exception("survey_generate_recommendations_failed order_id=%s", order_id)
            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc) from exc
            raise
