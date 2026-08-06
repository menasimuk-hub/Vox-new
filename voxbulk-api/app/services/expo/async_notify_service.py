"""Enqueue Expo completion notifications without depending on a fresh Celery worker.

Celery is used only when VOX_EXPO_EMAIL_CELERY=1. A successful .delay() is not enough if the
worker is outdated — unregistered tasks are dropped with no fallback. Default path uses a
daemon thread so catalogue / exhibitor mail leaves the request path quickly and still sends.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from sqlalchemy.orm import Session

from app.models.expo import ExpoBooth, ExpoLead

logger = logging.getLogger(__name__)


def _celery_email_enabled() -> bool:
    return str(os.environ.get("VOX_EXPO_EMAIL_CELERY") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _try_delay(task: Any, **kwargs: Any) -> bool:
    try:
        task.delay(**kwargs)
        return True
    except Exception as exc:
        logger.warning("expo_notify_enqueue_failed task=%s err=%s", getattr(task, "name", task), str(exc)[:200])
        return False


def _load_lead_booth(db: Session, lead_id: str) -> tuple[ExpoLead | None, ExpoBooth | None]:
    lead = db.get(ExpoLead, str(lead_id or "").strip())
    if lead is None:
        return None, None
    booth = db.get(ExpoBooth, lead.booth_id)
    return lead, booth


def _bg_visitor(lead_id: str, asset_ids: list[str]) -> None:
    from app.core.database import get_sessionmaker
    from app.services.expo.expo_email_service import ExpoEmailService
    from app.services.expo.offer_delivery_service import load_booth_assets

    try:
        with get_sessionmaker()() as db:
            lead, booth = _load_lead_booth(db, lead_id)
            if lead is None or booth is None:
                return
            assets = load_booth_assets(db, booth.id)
            wanted = {str(a) for a in asset_ids if a}
            if wanted:
                assets = [a for a in assets if str(a.get("id") or "") in wanted]
            ExpoEmailService.send_visitor_catalogue(db, booth=booth, lead=lead, assets=assets)
    except Exception:
        logger.exception("expo_visitor_catalogue_bg_failed lead=%s", lead_id)


def _bg_exhibitor(lead_id: str) -> None:
    from app.core.database import get_sessionmaker
    from app.services.expo.expo_email_service import ExpoEmailService
    from app.services.expo.session_flow_service import ExpoSessionFlowService

    try:
        with get_sessionmaker()() as db:
            lead, booth = _load_lead_booth(db, lead_id)
            if lead is None or booth is None:
                return
            delivered = ExpoSessionFlowService._delivered_assets_payload(db, booth=booth, lead=lead)
            ExpoEmailService.notify_exhibitor_lead(db, booth=booth, lead=lead, assets=delivered)
    except Exception:
        logger.exception("expo_exhibitor_lead_bg_failed lead=%s", lead_id)


def _bg_hot(lead_id: str) -> None:
    from app.core.database import get_sessionmaker
    from app.services.expo.hot_lead_notify_service import notify_hot_lead

    try:
        with get_sessionmaker()() as db:
            lead, booth = _load_lead_booth(db, lead_id)
            if lead is None or booth is None:
                return
            notify_hot_lead(db, booth=booth, lead=lead)
    except Exception:
        logger.exception("expo_hot_lead_bg_failed lead=%s", lead_id)


def enqueue_visitor_catalogue(
    db: Session,
    *,
    booth: ExpoBooth,
    lead: ExpoLead,
    assets: list[dict[str, Any]],
) -> str:
    """Queue visitor catalogue email off the request path."""
    from app.services.expo.expo_email_service import ExpoEmailService

    asset_ids = [str(a.get("id") or "") for a in assets if a.get("id")]
    if _celery_email_enabled():
        from app.workers.expo_notify_tasks import send_visitor_catalogue_task

        if _try_delay(send_visitor_catalogue_task, lead_id=lead.id, asset_ids=asset_ids):
            return "queued"
    try:
        threading.Thread(
            target=_bg_visitor,
            args=(str(lead.id), asset_ids),
            daemon=True,
            name=f"expo-visitor-mail-{lead.id[:8]}",
        ).start()
        return "threaded"
    except Exception:
        logger.exception("expo_visitor_catalogue_thread_failed lead=%s", lead.id)
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

    if _celery_email_enabled():
        from app.workers.expo_notify_tasks import notify_exhibitor_lead_task

        if _try_delay(notify_exhibitor_lead_task, lead_id=lead.id):
            return "queued"
    try:
        threading.Thread(
            target=_bg_exhibitor,
            args=(str(lead.id),),
            daemon=True,
            name=f"expo-exhibitor-mail-{lead.id[:8]}",
        ).start()
        return "threaded"
    except Exception:
        logger.exception("expo_exhibitor_lead_thread_failed lead=%s", lead.id)
        try:
            ok = ExpoEmailService.notify_exhibitor_lead(db, booth=booth, lead=lead, assets=assets or [])
            return "sent" if ok else "failed"
        except Exception:
            logger.exception("expo_exhibitor_lead_sync_fallback_failed lead=%s", lead.id)
            return "failed"


def enqueue_hot_lead(db: Session, *, booth: ExpoBooth, lead: ExpoLead) -> str:
    from app.services.expo.hot_lead_notify_service import notify_hot_lead

    if _celery_email_enabled():
        from app.workers.expo_notify_tasks import notify_hot_lead_task

        if _try_delay(notify_hot_lead_task, lead_id=lead.id):
            return "queued"
    try:
        threading.Thread(
            target=_bg_hot,
            args=(str(lead.id),),
            daemon=True,
            name=f"expo-hot-notify-{lead.id[:8]}",
        ).start()
        return "threaded"
    except Exception:
        logger.exception("expo_hot_lead_thread_failed lead=%s", lead.id)
        try:
            ok = notify_hot_lead(db, booth=booth, lead=lead)
            return "sent" if ok else "failed"
        except Exception:
            logger.exception("expo_hot_lead_sync_fallback_failed lead=%s", lead.id)
            return "failed"
