from __future__ import annotations

import json

from app.core.logging import get_logger
from app.core.database import get_sessionmaker
from app.services.gocardless_billing_webhook_service import apply_gocardless_billing_events
from app.services.recovery_service import WebhookEventService
from app.workers.celery_app import celery_app
from sqlalchemy import select

from app.models.webhook_event import WebhookEvent
from app.services.dentally import DentallyAdapter, DentallyError, DentallySyncService


logger = get_logger(__name__)


@celery_app.task(name="webhooks.vapi")
def handle_vapi_webhook(*, event_id: int) -> dict:
    with get_sessionmaker()() as db:
        WebhookEventService.mark_processing(db, event_id)
        WebhookEventService.mark_processed(db, event_id)
    logger.info("vapi_webhook_processed", extra={"event_id": event_id})
    return {"status": "processed", "event_id": event_id}


@celery_app.task(name="webhooks.gocardless")
def handle_gocardless_webhook(*, event_id: int) -> dict:
    summary: dict = {}
    with get_sessionmaker()() as db:
        WebhookEventService.mark_processing(db, event_id)
        event = db.execute(select(WebhookEvent).where(WebhookEvent.id == event_id)).scalar_one()
        try:
            data = json.loads(event.raw_body or "{}")
            if not isinstance(data, dict):
                data = {}
            evs = data.get("events") or []
            if not isinstance(evs, list):
                evs = []
            typed = [x for x in evs if isinstance(x, dict)]
            summary = apply_gocardless_billing_events(db, typed)
        except Exception as exc:
            logger.exception("gocardless_webhook_billing_handler_failed", extra={"event_id": event_id})
            db.rollback()
            WebhookEventService.mark_failed(db, event_id, str(exc))
            raise
        WebhookEventService.mark_processed(db, event_id)
    logger.info("gocardless_webhook_processed", extra={"event_id": event_id, "billing": summary})
    return {"status": "processed", "event_id": event_id, "billing": summary}


@celery_app.task(name="webhooks.retry_unprocessed")
def retry_unprocessed_webhooks() -> dict:
    from datetime import datetime, timedelta

    cutoff = datetime.utcnow() - timedelta(minutes=2)
    retried = 0
    with get_sessionmaker()() as db:
        rows = list(
            db.execute(
                select(WebhookEvent).where(
                    WebhookEvent.status.in_(("received", "failed")),
                    WebhookEvent.signature_valid.is_(True),
                    WebhookEvent.received_at <= cutoff,
                ).limit(50)
            ).scalars().all()
        )
        for row in rows:
            provider = str(row.provider or "").lower()
            try:
                if provider == "gocardless":
                    handle_gocardless_webhook.delay(event_id=row.id)
                elif provider == "vapi":
                    handle_vapi_webhook.delay(event_id=row.id)
                elif provider == "stripe":
                    from app.services.stripe_payment_service import StripePaymentService

                    payload = json.loads(row.raw_body or "{}")
                    StripePaymentService.handle_webhook_event(db, payload if isinstance(payload, dict) else {})
                    WebhookEventService.mark_processed(db, row.id)
                elif provider == "airwallex":
                    from app.services.airwallex_payment_service import AirwallexPaymentService

                    payload = json.loads(row.raw_body or "{}")
                    AirwallexPaymentService.handle_webhook_event(db, payload if isinstance(payload, dict) else {})
                    WebhookEventService.mark_processed(db, row.id)
                else:
                    continue
                retried += 1
            except Exception as exc:
                WebhookEventService.mark_failed(db, row.id, str(exc))
    return {"retried": retried}


@celery_app.task(name="dentally.sync_tenant")
def dentally_sync_tenant(*, org_id: str) -> dict:
    """
    On-demand sync foundation for minimal datasets.

    TODO: Add scheduling and rate limiting in later phases.
    """
    with get_sessionmaker()() as db:
        try:
            adapter = DentallyAdapter.from_settings()
        except DentallyError as e:
            return {"ok": False, "error": str(e)}

        branches = DentallySyncService.sync_branches(db, org_id=org_id, adapter=adapter)
        patients = DentallySyncService.sync_patients(db, org_id=org_id, adapter=adapter)
        appointments = DentallySyncService.sync_appointments(db, org_id=org_id, adapter=adapter)

        return {
            "ok": True,
            "branches": branches.__dict__,
            "patients": patients.__dict__,
            "appointments": appointments.__dict__,
        }

