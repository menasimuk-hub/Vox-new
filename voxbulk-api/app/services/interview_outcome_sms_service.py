"""Phone-path outcome SMS/WhatsApp (candidate 'end screen' when there is no web UI)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.telnyx_messaging_service import TelnyxMessagingService

logger = logging.getLogger(__name__)

_OUTCOME_SMS = {
    "reschedule": (
        "Thanks — no problem. Please use the link in your email to pick a new interview time."
    ),
    "recording_declined": (
        "Thanks for letting us know. We cannot continue without recording consent, so this interview is closed."
    ),
    "wrong_person": "Sorry for the interruption — please disregard this call.",
    "technical_abort": (
        "The call ended early. If your booking slot is still open, you can rejoin from your booking link or email."
    ),
    "completed": (
        "Thank you for your time today. Our team will review your answers and be in touch about next steps."
    ),
}


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def maybe_send_interview_outcome_sms(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    outcome: str,
    channel: str,
) -> dict[str, Any]:
    """Send one SMS/WA outcome notice for phone interviews (idempotent)."""
    if str(channel or "").strip().lower() not in {"ai_call", "phone", "call"}:
        return {"skipped": True, "reason": "not_phone_channel"}
    outcome_key = str(outcome or "").strip().lower()
    body = _OUTCOME_SMS.get(outcome_key)
    if not body:
        return {"skipped": True, "reason": "no_template"}
    phone = str(recipient.phone or "").strip()
    if not phone:
        return {"skipped": True, "reason": "no_phone"}

    existing = _loads(recipient.result_json)
    if existing.get("outcome_sms_sent_at") and existing.get("outcome_sms_outcome") == outcome_key:
        return {"skipped": True, "reason": "already_sent"}

    result = TelnyxMessagingService.send_survey_message(
        db,
        org_id=order.org_id,
        to_number=phone,
        body=body,
        prefer_whatsapp=True,
    )
    merged = dict(existing)
    merged.update(
        {
            "outcome_sms_attempted_at": datetime.utcnow().isoformat(),
            "outcome_sms_outcome": outcome_key,
            "outcome_sms_ok": bool(result.ok),
            "outcome_sms_channel": result.channel if result.ok else None,
            "outcome_sms_status": result.status,
            "outcome_sms_detail": result.detail,
        }
    )
    if result.ok:
        merged["outcome_sms_sent_at"] = datetime.utcnow().isoformat()
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    recipient.updated_at = datetime.utcnow()
    db.add(recipient)
    db.commit()
    if not result.ok:
        logger.warning(
            "interview_outcome_sms_failed order=%s recipient=%s status=%s detail=%s",
            order.id,
            recipient.id,
            result.status,
            result.detail,
        )
    return {"ok": bool(result.ok), "channel": result.channel, "status": result.status}
