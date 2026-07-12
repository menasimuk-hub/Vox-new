"""Post-session interview WhatsApp notices — approved HSM templates only (no SMS / free text)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.interview_booking_service import InterviewBookingService, _first_name
from app.services.interview_whatsapp_send_service import InterviewWhatsappSendService
from app.services.telnyx_messaging_service import TelnyxMessagingService

logger = logging.getLogger(__name__)


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def maybe_send_interview_outcome_whatsapp(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    outcome: str,
    channel: str,
) -> dict[str, Any]:
    """Send one approved interview WA template after a phone session (idempotent).

    Mapping (existing templates only):
    - reschedule / technical_abort → interview_email_sent (book via email)
    - recording_declined → interview_job_closed (process closed for candidate)
    - completed / wrong_person → no WA (email covers thank-you / no suitable template)
    """
    if str(channel or "").strip().lower() not in {"ai_call", "phone", "call"}:
        return {"skipped": True, "reason": "not_phone_channel"}

    outcome_key = str(outcome or "").strip().lower()
    if outcome_key in {"completed", "wrong_person"}:
        return {"skipped": True, "reason": "no_wa_template_for_outcome"}

    phone = str(recipient.phone or "").strip()
    if not phone:
        return {"skipped": True, "reason": "no_phone"}

    existing = _loads(recipient.result_json)
    if existing.get("outcome_wa_sent_at") and existing.get("outcome_wa_outcome") == outcome_key:
        return {"skipped": True, "reason": "already_sent"}

    try:
        cfg = json.loads(order.config_json or "{}")
        role = str((cfg or {}).get("role") or order.title or "Interview").strip()
    except Exception:
        role = str(order.title or "Interview").strip()
    company = InterviewBookingService._org_name(db, order)
    first = _first_name(recipient.name)
    careers_from = "careers@voxbulk.com"

    template_row = None
    components: list[dict[str, Any]] | None = None
    log_label = ""

    if outcome_key in {"reschedule", "technical_abort"}:
        template_row = InterviewBookingService.resolve_invite_wa_template(db, order)
        if template_row is None:
            return {"skipped": True, "reason": "missing_email_sent_template"}
        components = InterviewBookingService.build_email_sent_components(
            template_row,
            candidate_name=recipient.name or "Candidate",
            role=role,
            company_name=company,
            careers_email=careers_from,
        )
        log_label = template_row.name
    elif outcome_key == "recording_declined":
        template_row = InterviewBookingService.resolve_job_closed_template(db, order)
        if template_row is None:
            return {"skipped": True, "reason": "missing_job_closed_template"}
        components = InterviewBookingService.build_job_closed_components(
            template_row,
            candidate_name=recipient.name or "Candidate",
            role=role,
            company_name=company,
        )
        log_label = template_row.name
    else:
        return {"skipped": True, "reason": f"unsupported_outcome:{outcome_key}"}

    log_body = f"[template:{log_label}] outcome={outcome_key} candidate={first}"
    result = InterviewWhatsappSendService.send_template_or_plain(
        db,
        to_number=phone,
        body=log_body,
        org_id=order.org_id,
        template_row=template_row,
        template_components=components,
        template_language=template_row.language or "en_US",
        require_template=True,
    )

    merged = dict(existing)
    merged.update(
        {
            "outcome_wa_attempted_at": datetime.utcnow().isoformat(),
            "outcome_wa_outcome": outcome_key,
            "outcome_wa_template": log_label,
            "outcome_wa_ok": bool(result.ok),
            "outcome_wa_channel": result.channel if result.ok else None,
            "outcome_wa_status": result.status,
            "outcome_wa_detail": result.detail,
        }
    )
    if result.ok:
        merged["outcome_wa_sent_at"] = datetime.utcnow().isoformat()
        TelnyxMessagingService.log_outbound(
            db,
            org_id=order.org_id,
            to_number=phone,
            from_number=None,
            body=log_body,
            result=result,
        )
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    recipient.updated_at = datetime.utcnow()
    db.add(recipient)
    db.commit()
    if not result.ok:
        logger.warning(
            "interview_outcome_wa_failed order=%s recipient=%s template=%s detail=%s",
            order.id,
            recipient.id,
            log_label,
            result.detail,
        )
    return {
        "ok": bool(result.ok),
        "channel": result.channel,
        "status": result.status,
        "template": log_label,
    }
