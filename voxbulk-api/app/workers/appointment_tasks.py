"""Celery tasks for AI Appointment Manager."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.core.logging import get_logger
from app.models.appointment import Appointment
from app.models.organisation import Organisation
from app.services.appointment_crm_sync_service import sync_all_orgs, sync_org_appointments
from app.services.appointment_settings_service import get_config
from app.services.appointment_wa_service import send_confirmation
from app.services.org_enabled_services import is_service_enabled, org_service_maps
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


def _orgs_with_appointments(db):
    orgs = list(db.execute(select(Organisation).where(Organisation.deletion_status == "active")).scalars())
    out = []
    for org in orgs:
        _allowed, _enabled, visible = org_service_maps(org, db)
        if is_service_enabled(visible, "appointments"):
            out.append(org)
    return out


@celery_app.task(name="appointments.sync_crm_appointments")
def sync_crm_appointments(org_id: str | None = None) -> dict:
    with get_sessionmaker()() as db:
        if org_id:
            result = sync_org_appointments(db, org_id)
        else:
            result = sync_all_orgs(db)
    logger.info("appointment_crm_sync %s", result)
    return result


@celery_app.task(name="appointments.scan_confirmation_windows")
def scan_confirmation_windows() -> dict:
    now = datetime.utcnow()
    sent_wa = 0
    triggered_calls = 0
    with get_sessionmaker()() as db:
        for org in _orgs_with_appointments(db):
            cfg = get_config(db, org.id)
            wa_hours = int(cfg.get("wa_send_hours_before") or 72)
            call_hours = int(cfg.get("call_hours_before") or 24)

            if cfg.get("wa_enabled"):
                wa_cutoff = now + timedelta(hours=wa_hours)
                rows = list(
                    db.execute(
                        select(Appointment).where(
                            Appointment.org_id == org.id,
                            Appointment.status == "scheduled",
                            Appointment.wa_confirmation_sent_at.is_(None),
                            Appointment.appointment_datetime <= wa_cutoff,
                            Appointment.appointment_datetime > now,
                        )
                    ).scalars()
                )
                for appt in rows:
                    try:
                        res = send_confirmation(db, appt.id)
                        if res.get("ok"):
                            sent_wa += 1
                    except Exception:
                        logger.exception("appointment_wa_scan_failed appointment_id=%s", appt.id)

            if cfg.get("call_enabled"):
                from app.services.appointment_call_service import initiate_confirmation_call

                call_cutoff = now + timedelta(hours=call_hours)
                rows = list(
                    db.execute(
                        select(Appointment).where(
                            Appointment.org_id == org.id,
                            Appointment.status.in_(("scheduled", "rescheduled")),
                            Appointment.call_triggered_at.is_(None),
                            Appointment.appointment_datetime <= call_cutoff,
                            Appointment.appointment_datetime > now,
                        )
                    ).scalars()
                )
                for appt in rows:
                    try:
                        res = initiate_confirmation_call(db, appt.id)
                        if res.get("ok"):
                            triggered_calls += 1
                    except Exception:
                        logger.exception("appointment_call_scan_failed appointment_id=%s", appt.id)

    result = {"sent_wa": sent_wa, "triggered_calls": triggered_calls}
    logger.info("appointment_confirmation_scan %s", result)
    return result


@celery_app.task(name="appointments.send_wa_confirmation")
def send_wa_confirmation(appointment_id: str) -> dict:
    with get_sessionmaker()() as db:
        result = send_confirmation(db, appointment_id)
    logger.info("appointment_send_wa appointment_id=%s ok=%s", appointment_id, result.get("ok"))
    return result


@celery_app.task(name="appointments.scan_reminder_sequences")
def scan_reminder_sequences() -> dict:
    now = datetime.utcnow()
    sent = 0
    with get_sessionmaker()() as db:
        for org in _orgs_with_appointments(db):
            cfg = get_config(db, org.id)
            sequence = cfg.get("reminder_sequence_json") or []
            if not isinstance(sequence, list):
                continue
            for step in sequence:
                if not isinstance(step, dict):
                    continue
                hours = int(step.get("hours_before") or 0)
                channel = str(step.get("channel") or "").strip().lower()
                if hours <= 0 or channel != "whatsapp":
                    continue
                cutoff = now + timedelta(hours=hours)
                rows = list(
                    db.execute(
                        select(Appointment).where(
                            Appointment.org_id == org.id,
                            Appointment.status.in_(("scheduled", "confirmed")),
                            Appointment.appointment_datetime <= cutoff,
                            Appointment.appointment_datetime > now,
                        )
                    ).scalars()
                )
                for appt in rows:
                    try:
                        res = send_confirmation(db, appt.id)
                        if res.get("ok"):
                            sent += 1
                    except Exception:
                        logger.exception("appointment_reminder_failed appointment_id=%s", appt.id)
    result = {"sent": sent}
    logger.info("appointment_reminder_scan %s", result)
    return result
