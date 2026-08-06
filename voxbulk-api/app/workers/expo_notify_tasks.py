"""Celery tasks — Expo completion emails and hot-lead notify (off the request path)."""

from __future__ import annotations

import logging
from typing import Any

from app.core.database import get_sessionmaker
from app.models.expo import ExpoBooth, ExpoLead
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _load_lead_booth(db, lead_id: str) -> tuple[ExpoLead | None, ExpoBooth | None]:
    lead = db.get(ExpoLead, str(lead_id or "").strip())
    if lead is None:
        return None, None
    booth = db.get(ExpoBooth, lead.booth_id)
    return lead, booth


@celery_app.task(name="expo.send_visitor_catalogue", bind=True, max_retries=2, default_retry_delay=30)
def send_visitor_catalogue_task(self, lead_id: str, asset_ids: list[str] | None = None) -> dict[str, Any]:
    from app.services.expo.expo_email_service import ExpoEmailService
    from app.services.expo.offer_delivery_service import load_booth_assets

    with get_sessionmaker()() as db:
        lead, booth = _load_lead_booth(db, lead_id)
        if lead is None or booth is None:
            return {"ok": False, "error": "not_found"}
        assets = load_booth_assets(db, booth.id)
        wanted = {str(a) for a in (asset_ids or []) if a}
        if wanted:
            assets = [a for a in assets if str(a.get("id") or "") in wanted]
        ok = ExpoEmailService.send_visitor_catalogue(db, booth=booth, lead=lead, assets=assets)
        return {"ok": bool(ok), "lead_id": lead.id}


@celery_app.task(name="expo.notify_exhibitor_lead", bind=True, max_retries=2, default_retry_delay=30)
def notify_exhibitor_lead_task(self, lead_id: str) -> dict[str, Any]:
    from app.services.expo.expo_email_service import ExpoEmailService
    from app.services.expo.session_flow_service import ExpoSessionFlowService

    with get_sessionmaker()() as db:
        lead, booth = _load_lead_booth(db, lead_id)
        if lead is None or booth is None:
            return {"ok": False, "error": "not_found"}
        delivered = ExpoSessionFlowService._delivered_assets_payload(db, booth=booth, lead=lead)
        ok = ExpoEmailService.notify_exhibitor_lead(db, booth=booth, lead=lead, assets=delivered)
        return {"ok": bool(ok), "lead_id": lead.id}


@celery_app.task(name="expo.notify_hot_lead", bind=True, max_retries=2, default_retry_delay=20)
def notify_hot_lead_task(self, lead_id: str) -> dict[str, Any]:
    from app.services.expo.hot_lead_notify_service import notify_hot_lead

    with get_sessionmaker()() as db:
        lead, booth = _load_lead_booth(db, lead_id)
        if lead is None or booth is None:
            return {"ok": False, "error": "not_found"}
        ok = notify_hot_lead(db, booth=booth, lead=lead)
        return {"ok": bool(ok), "lead_id": lead.id}
