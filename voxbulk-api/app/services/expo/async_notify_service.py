"""Enqueue Expo completion notifications on Celery with sync fallback."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.expo import ExpoBooth, ExpoLead

logger = logging.getLogger(__name__)


def _try_delay(task: Any, **kwargs: Any) -> bool:
    try:
        task.delay(**kwargs)
        return True
    except Exception as exc:
        logger.warning("expo_notify_enqueue_failed task=%s err=%s", getattr(task, "name", task), str(exc)[:200])
        return False


def enqueue_visitor_catalogue(
    db: Session,
    *,
    booth: ExpoBooth,
    lead: ExpoLead,
    assets: list[dict[str, Any]],
) -> str:
    """Queue visitor catalogue email; run inline if Celery is unavailable."""
    from app.services.expo.expo_email_service import ExpoEmailService
    from app.workers.expo_notify_tasks import send_visitor_catalogue_task

    asset_ids = [str(a.get("id") or "") for a in assets if a.get("id")]
    if _try_delay(send_visitor_catalogue_task, lead_id=lead.id, asset_ids=asset_ids):
        return "queued"
    try:
        ok = ExpoEmailService.send_visitor_catalogue(db, booth=booth, lead=lead, assets=assets)
        return "sent" if ok else "failed"
    except Exception:
        logger.exception("expo_visitor_catalogue_sync_fallback_failed lead=%s", lead.id)
        return "failed"


def enqueue_exhibitor_lead(
    db: Session,
    *,
    booth: ExpoBooth,
    lead: ExpoLead,
    assets: list[dict[str, Any]] | None = None,
) -> str:
    from app.services.expo.expo_email_service import ExpoEmailService
    from app.workers.expo_notify_tasks import notify_exhibitor_lead_task

    if _try_delay(notify_exhibitor_lead_task, lead_id=lead.id):
        return "queued"
    try:
        ok = ExpoEmailService.notify_exhibitor_lead(db, booth=booth, lead=lead, assets=assets or [])
        return "sent" if ok else "failed"
    except Exception:
        logger.exception("expo_exhibitor_lead_sync_fallback_failed lead=%s", lead.id)
        return "failed"


def enqueue_hot_lead(db: Session, *, booth: ExpoBooth, lead: ExpoLead) -> str:
    from app.services.expo.hot_lead_notify_service import notify_hot_lead
    from app.workers.expo_notify_tasks import notify_hot_lead_task

    if _try_delay(notify_hot_lead_task, lead_id=lead.id):
        return "queued"
    try:
        ok = notify_hot_lead(db, booth=booth, lead=lead)
        return "sent" if ok else "failed"
    except Exception:
        logger.exception("expo_hot_lead_sync_fallback_failed lead=%s", lead.id)
        return "failed"
