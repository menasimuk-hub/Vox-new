"""Celery tasks for WA survey answer translation."""

from __future__ import annotations

from app.core.database import get_sessionmaker
from app.core.logging import get_logger
from app.services.survey_wa_translation_service import SurveyWaTranslationService
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="survey.translate_wa_answer", bind=True, max_retries=2, default_retry_delay=20)
def translate_wa_answer_task(
    self,
    *,
    recipient_id: str,
    voice_note_job_id: str | None = None,
    answer_index: int | None = None,
) -> dict:
    with get_sessionmaker()() as db:
        try:
            result = SurveyWaTranslationService.process_recipient_translation(
                db,
                recipient_id,
                voice_note_job_id=voice_note_job_id,
                answer_index=answer_index,
            )
            if not result.get("ok") and self.request.retries < self.max_retries:
                raise self.retry(exc=RuntimeError(str(result.get("error") or "translation failed")))
            return result
        except Exception as exc:
            logger.exception("survey_translate_wa_answer_failed recipient_id=%s", recipient_id)
            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc) from exc
            raise
