"""Celery tasks for WhatsApp survey voice-note transcription."""

from __future__ import annotations

from app.core.database import get_sessionmaker
from app.core.logging import get_logger
from app.services.survey_wa_voice_note_service import SurveyWaVoiceNoteService
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="survey.transcribe_voice_note", bind=True, max_retries=2, default_retry_delay=30)
def transcribe_survey_voice_note(self, *, job_id: str) -> dict:
    with get_sessionmaker()() as db:
        try:
            result = SurveyWaVoiceNoteService.process_transcription_job(db, job_id)
            if not result.get("ok") and self.request.retries < self.max_retries:
                raise self.retry(exc=RuntimeError(str(result.get("error") or "transcription failed")))
            return result
        except Exception as exc:
            logger.exception("survey_voice_note_task_failed job_id=%s", job_id)
            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc) from exc
            raise


@celery_app.task(name="survey.purge_voice_note_audio")
def purge_voice_note_audio() -> dict:
    with get_sessionmaker()() as db:
        count = SurveyWaVoiceNoteService.purge_expired_audio(db)
    return {"purged_jobs": count}
