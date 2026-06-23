"""Send post-visit WhatsApp surveys to appointment contacts."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.appointment_log_service import append_log
from app.services.appointment_settings_service import get_config
from app.services.platform_catalog_service import ServiceOrderService

logger = logging.getLogger(__name__)


def _effective_appointment_time(appt: Appointment) -> datetime | None:
    target = appt.rescheduled_to_datetime or appt.appointment_datetime
    return target if isinstance(target, datetime) else None


def _load_survey_config(order: ServiceOrder) -> dict:
    try:
        data = json.loads(order.config_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _find_or_create_recipient(
    db: Session,
    *,
    order: ServiceOrder,
    phone: str,
    name: str,
) -> ServiceOrderRecipient:
    from app.services.messaging_log_service import normalize_e164

    normalized_target = phone
    try:
        normalized_target = normalize_e164(phone)
    except ValueError:
        pass

    for row in ServiceOrderService.get_recipients(db, order.id):
        try:
            if normalize_e164(row.phone or "") == normalized_target:
                return row
        except ValueError:
            if str(row.phone or "").strip() == phone:
                return row

    next_row = len(ServiceOrderService.get_recipients(db, order.id)) + 1
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=next_row,
        name=name or "Patient",
        phone=normalized_target,
        status="pending",
    )
    db.add(recipient)
    db.flush()
    return recipient


def send_post_visit_survey(db: Session, appt: Appointment) -> dict:
    cfg = get_config(db, appt.org_id)
    if not cfg.get("post_survey_enabled"):
        return {"skipped": True, "reason": "disabled"}
    if appt.post_survey_sent_at is not None:
        return {"skipped": True, "reason": "already_sent"}

    order_id = str(cfg.get("post_survey_order_id") or "").strip()
    if not order_id:
        return {"skipped": True, "reason": "no_survey_selected"}

    order = db.get(ServiceOrder, order_id)
    if order is None or str(order.org_id) != str(appt.org_id):
        return {"skipped": True, "reason": "survey_not_found"}
    if order.service_code != "survey":
        return {"skipped": True, "reason": "not_survey_order"}

    config = _load_survey_config(order)
    if not config:
        return {"skipped": True, "reason": "empty_survey_config"}

    now = datetime.utcnow()
    if order.status not in {"running", "scheduled", "draft", "approved"}:
        if order.status in {"completed", "stopped", "archived"}:
            return {"skipped": True, "reason": f"survey_status_{order.status}"}
    if order.status in {"draft", "approved"}:
        order.status = "running"
        order.started_at = order.started_at or now
        order.updated_at = now
        db.add(order)

    first_name = str(appt.contact_name or "").strip().split()[0] if appt.contact_name else "there"
    recipient = _find_or_create_recipient(
        db,
        order=order,
        phone=appt.contact_phone,
        name=first_name,
    )
    recipient.name = first_name or recipient.name
    recipient.status = "pending"
    recipient.updated_at = now
    db.add(recipient)
    db.flush()

    from app.services.survey_whatsapp_conversation_service import send_survey_opening

    sent = send_survey_opening(db, order=order, recipient=recipient, config=config)
    if not sent:
        return {"ok": False, "reason": "survey_opening_failed"}

    appt.post_survey_sent_at = now
    appt.updated_at = now
    db.add(appt)
    append_log(
        db,
        appointment_id=appt.id,
        event_type="post_survey_sent",
        detail={"order_id": order.id, "recipient_id": recipient.id},
    )
    db.commit()
    return {"ok": True, "order_id": order.id, "recipient_id": recipient.id}


def scan_post_visit_surveys(db: Session, org_id: str) -> dict:
    cfg = get_config(db, org_id)
    if not cfg.get("post_survey_enabled"):
        return {"org_id": org_id, "sent": 0, "skipped": True}

    delay_hours = int(cfg.get("post_survey_delay_hours") or 2)
    now = datetime.utcnow()
    cutoff = now - timedelta(hours=delay_hours)
    sent = 0

    rows = list(
        db.execute(
            select(Appointment).where(
                Appointment.org_id == org_id,
                Appointment.post_survey_sent_at.is_(None),
                Appointment.status.in_(("scheduled", "confirmed", "rescheduled")),
            )
        ).scalars()
    )
    for appt in rows:
        effective = _effective_appointment_time(appt)
        if effective is None or effective > cutoff:
            continue
        try:
            result = send_post_visit_survey(db, appt)
            if result.get("ok"):
                sent += 1
        except Exception:
            logger.exception("post_visit_survey_failed appointment_id=%s", appt.id)
            db.rollback()
    return {"org_id": org_id, "sent": sent}


def scan_all_orgs_post_visit_surveys(db: Session) -> dict:
    from app.models.organisation import Organisation
    from app.services.org_enabled_services import is_service_enabled, org_service_maps

    orgs = list(db.execute(select(Organisation).where(Organisation.deletion_status == "active")).scalars())
    results: list[dict] = []
    total_sent = 0
    for org in orgs:
        _allowed, _enabled, visible = org_service_maps(org, db)
        if not is_service_enabled(visible, "appointments"):
            continue
        try:
            row = scan_post_visit_surveys(db, org.id)
            results.append(row)
            total_sent += int(row.get("sent") or 0)
        except Exception:
            logger.exception("post_visit_survey_scan_failed org=%s", org.id)
    return {"orgs_scanned": len(results), "sent": total_sent, "results": results}
