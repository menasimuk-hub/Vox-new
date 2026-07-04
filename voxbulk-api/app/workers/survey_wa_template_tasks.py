"""Celery tasks for WA survey template lifecycle (supersede cleanup)."""

from __future__ import annotations

from app.core.database import get_sessionmaker
from app.services.survey_wa_template_supersede_service import process_one_superseded_template_deletion
from app.workers.celery_app import celery_app


@celery_app.task(name="survey.cleanup_superseded_wa_templates")
def cleanup_superseded_wa_templates() -> dict:
    with get_sessionmaker()() as db:
        return process_one_superseded_template_deletion(db)
