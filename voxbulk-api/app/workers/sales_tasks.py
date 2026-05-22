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


@celery_app.task(name="sales.retry_post_call_automation")
def retry_post_call_automation_task(task_id: str) -> dict:
    """Re-sync Telnyx transcript/outcome and run post-call offer automation."""
    with get_sessionmaker()() as db:
        from app.models.lead_sales_task import LeadSalesTask
        from app.services.lead_sales_outcome_service import sync_sales_task_outcome
        from app.services.sales_automation_service import SalesAutomationService

        task = db.get(LeadSalesTask, task_id)
        if task is None:
            return {"ok": False, "skipped": True, "reason": "task_not_found"}
        if task.offer_sent_at:
            return {"ok": False, "skipped": True, "reason": "offer_already_sent"}
        try:
            task = sync_sales_task_outcome(db, task)
        except Exception as exc:
            logger.warning("retry_outcome_sync_failed", extra={"task_id": task_id, "error": str(exc)})
            SalesAutomationService._set_task_error(db, task, f"Outcome sync failed: {exc}")
            return {"ok": False, "error": str(exc)}
        result = SalesAutomationService.run_post_call_automation(db, task, call_status=str(task.status or "completed"))
        logger.info("retry_post_call_automation_complete", extra={"task_id": task_id, **result})
        return result
