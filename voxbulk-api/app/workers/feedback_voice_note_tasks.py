"""Celery tasks for Customer Feedback voice-note transcription."""

from __future__ import annotations

from app.core.database import get_sessionmaker
from app.core.logging import get_logger
from app.services.customer_feedback.feedback_voice_note_service import process_voice_job
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="feedback.transcribe_voice_note", bind=True, max_retries=2, default_retry_delay=30)
def transcribe_feedback_voice_note(self, *, job_id: str) -> dict:
    with get_sessionmaker()() as db:
        try:
            result = process_voice_job(db, job_id)
            if not result.get("ok") and self.request.retries < self.max_retries:
                raise self.retry(exc=RuntimeError(str(result.get("error") or "transcription failed")))
            return result
        except Exception as exc:
            logger.exception("feedback_voice_note_task_failed job_id=%s", job_id)
            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc) from exc
            raise
