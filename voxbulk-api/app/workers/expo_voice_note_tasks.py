"""Celery task — Expo voice note transcription."""

from __future__ import annotations

import logging

from app.core.database import get_sessionmaker
from app.services.expo.voice_note_service import process_expo_voice_job
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="expo.transcribe_voice_note", bind=True, max_retries=2)
def transcribe_expo_voice_note(self, *, job_id: str) -> dict:
    db = get_sessionmaker()()
    try:
        return process_expo_voice_job(db, job_id)
    except Exception as exc:
        logger.exception("expo_voice_note_task_failed job_id=%s", job_id)
        raise self.retry(exc=exc, countdown=20) from exc
    finally:
        db.close()
