"""Celery tasks for WA survey template lifecycle (status sync, supersede cleanup)."""

from __future__ import annotations

from app.core.database import get_sessionmaker
from app.services.survey_wa_template_supersede_service import (
    process_one_superseded_template_deletion,
    sync_pending_wa_templates_if_any,
    sync_wa_template_statuses_from_meta,
)
from app.workers.celery_app import celery_app


@celery_app.task(name="survey.cleanup_superseded_wa_templates")
def cleanup_superseded_wa_templates() -> dict:
    with get_sessionmaker()() as db:
        return process_one_superseded_template_deletion(db)


@celery_app.task(name="survey.sync_wa_template_meta_statuses")
def sync_wa_template_meta_statuses() -> dict:
    """Refresh local APPROVED/PENDING from Meta; deactivate duplicate clone siblings."""
    with get_sessionmaker()() as db:
        return sync_wa_template_statuses_from_meta(db)


@celery_app.task(name="survey.sync_pending_wa_templates_if_any")
def sync_pending_wa_templates_if_any_task() -> dict:
    """Every 30m: sync Meta statuses only when survey templates are pending approval."""
    with get_sessionmaker()() as db:
        return sync_pending_wa_templates_if_any(db)
