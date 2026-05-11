from __future__ import annotations

import json
from urllib.parse import parse_qs

from app.core.logging import get_logger
from app.core.database import get_sessionmaker
from app.services.gocardless_billing_webhook_service import apply_gocardless_billing_events
from app.services.recovery_service import WebhookEventService
from app.workers.celery_app import celery_app
from sqlalchemy import select

from app.models.webhook_event import WebhookEvent
from app.models.recovery_job import RecoveryJob
from app.models.call_log import CallLog
from app.models.appointment import Appointment
from app.services.recovery_service import RecoveryStateMachine
from app.services.dentally import DentallyAdapter, DentallyError, DentallySyncService


logger = get_logger(__name__)


@celery_app.task(name="webhooks.twilio")
def handle_twilio_webhook(*, event_id: int) -> dict:
    with get_sessionmaker()() as db:
        WebhookEventService.mark_processing(db, event_id)
        event = db.execute(select(WebhookEvent).where(WebhookEvent.id == event_id)).scalar_one()
        parsed = parse_qs(event.raw_body, keep_blank_values=True)
        call_sid = (parsed.get("CallSid") or [None])[0]
        call_status = (parsed.get("CallStatus") or [None])[0]
        msg_sid = (parsed.get("MessageSid") or [None])[0]
        msg_status = (parsed.get("MessageStatus") or [None])[0]

        if call_sid:
            # Update call log if exists
            log = db.execute(select(CallLog).where(CallLog.external_call_id == call_sid)).scalar_one_or_none()
            if log is not None:
                log.status = str(call_status or log.status)
                # keep latest callback snapshot for inspection
                log.raw_payload = event.raw_body
                db.add(log)

            job = db.execute(
                select(RecoveryJob).where(RecoveryJob.provider == "twilio", RecoveryJob.provider_ref == call_sid)
            ).scalar_one_or_none()
            if job is not None:
                job.provider_status = str(call_status) if call_status else job.provider_status
                appt = db.execute(
                    select(Appointment).where(Appointment.id == job.appointment_id, Appointment.org_id == job.org_id)
                ).scalar_one()

                # deterministic mapping
                # We never mark "recovered" from Twilio alone; "completed" only means contacted.
                desired_appt_state: str | None = None
                desired_job_state: str | None = None
                terminal_error: str | None = None

                if call_status in {"queued", "initiated", "ringing", "in-progress", "answered"}:
                    desired_appt_state = "calling"
                    desired_job_state = "calling"
                elif call_status in {"completed"}:
                    desired_appt_state = "messaged"
                    desired_job_state = "messaged"
                elif call_status in {"busy", "no-answer", "failed", "canceled"}:
                    desired_appt_state = "failed"
                    desired_job_state = "failed"
                    terminal_error = f"Twilio: {call_status}"
                else:
                    # Unknown statuses are recorded but do not change state.
                    desired_appt_state = None
                    desired_job_state = None

                # Out-of-order/duplicate safety: do not regress terminal or later states.
                appt_rank = {"pending": 0, "queued": 1, "calling": 2, "messaged": 3, "recovered": 4, "failed": 4, "skipped": 4}
                if desired_appt_state is not None:
                    if appt_rank.get(desired_appt_state, 0) >= appt_rank.get(appt.recovery_state, 0):
                        try:
                            if desired_appt_state != appt.recovery_state:
                                RecoveryStateMachine.transition(
                                    db,
                                    appointment=appt,
                                    to_state=desired_appt_state,
                                    error=terminal_error,
                                )
                        except ValueError:
                            # Invalid transition (e.g. queued->messaged) should be a no-op.
                            pass

                if desired_job_state is not None:
                    job_rank = {"queued": 0, "calling": 1, "messaged": 2, "recovered": 3, "failed": 3, "skipped": 3}
                    if job_rank.get(desired_job_state, 0) >= job_rank.get(job.state, 0):
                        job.state = desired_job_state
                        if terminal_error:
                            job.last_error = terminal_error
                        if desired_job_state in {"failed", "skipped", "messaged", "recovered"}:
                            job.finished_at = job.finished_at or appt.recovery_updated_at

                db.add(job)

        if msg_sid and msg_status:
            from app.models.whatsapp_log import WhatsAppLog

            wlog = db.execute(select(WhatsAppLog).where(WhatsAppLog.external_message_id == msg_sid)).scalar_one_or_none()
            if wlog is not None:
                wlog.status = str(msg_status)
                wlog.raw_payload = event.raw_body
                db.add(wlog)

            job = db.execute(
                select(RecoveryJob).where(RecoveryJob.provider == "twilio_whatsapp", RecoveryJob.provider_ref == msg_sid)
            ).scalar_one_or_none()
            if job is not None:
                job.provider_status = str(msg_status)
                db.add(job)

        try:
            WebhookEventService.mark_processed(db, event_id)
            db.commit()
        except Exception as exc:
            db.rollback()
            WebhookEventService.mark_failed(db, event_id, str(exc))
            raise

    logger.info(
        "twilio_webhook_processed",
        extra={"event_id": event_id, "call_sid": call_sid, "call_status": call_status, "message_sid": msg_sid, "message_status": msg_status},
    )
    return {"status": "processed", "event_id": event_id}


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

