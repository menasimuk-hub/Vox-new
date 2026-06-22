"""Send WhatsApp appointment confirmation templates."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.services.appointment_billing_service import AppointmentBillingError, AppointmentBillingService
from app.services.appointment_log_service import append_log
from app.services.appointment_settings_service import get_config
from app.services.telnyx_messaging_service import TelnyxMessagingService

logger = logging.getLogger(__name__)


def send_confirmation(db: Session, appointment_id: str) -> dict:
    appt = db.get(Appointment, appointment_id)
    if appt is None:
        raise ValueError("Appointment not found")

    cfg = get_config(db, appt.org_id)
    if not cfg.get("wa_enabled"):
        return {"ok": False, "reason": "wa_disabled"}

    try:
        AppointmentBillingService.assert_can_operate(db, appt.org_id)
    except AppointmentBillingError as exc:
        return {"ok": False, "reason": "billing_blocked", "detail": str(exc)}

    template_name = str(cfg.get("wa_template_name") or "appt_confirm_v1")
    body = (
        f"Hi {appt.contact_name}, please confirm your appointment on "
        f"{appt.appointment_datetime.strftime('%d %b %Y at %H:%M')}."
    )

    result = TelnyxMessagingService.send_whatsapp(
        db,
        to_number=appt.contact_phone,
        body=body,
        template_name=template_name,
        template_language="en_GB",
        org_id=appt.org_id,
        meter_usage=True,
    )

    now = datetime.utcnow()
    appt.wa_confirmation_sent_at = now
    appt.wa_confirmation_status = "delivered" if result.ok else "pending"
    appt.updated_at = now
    db.add(appt)
    append_log(
        db,
        appointment_id=appt.id,
        event_type="wa_confirmation_sent",
        detail={"ok": result.ok, "status": result.status, "template": template_name},
    )
    db.commit()
    db.refresh(appt)

    if not result.ok:
        logger.warning(
            "appointment_wa_send_failed appointment_id=%s status=%s detail=%s",
            appointment_id,
            result.status,
            result.detail,
        )
    return {"ok": result.ok, "status": result.status, "appointment_id": appt.id}
