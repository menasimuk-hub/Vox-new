"""Celery tasks for WA survey template lifecycle (supersede cleanup)."""

from __future__ import annotations

from app.core.database import SessionLocal
from app.services.survey_wa_template_supersede_service import process_one_superseded_template_deletion
from app.workers.celery_app import celery_app


@celery_app.task(name="survey.cleanup_superseded_wa_templates")
def cleanup_superseded_wa_templates() -> dict:
    db = SessionLocal()
    try:
        return process_one_superseded_template_deletion(db)
    finally:
        db.close()
