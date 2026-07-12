"""WhatsApp template retry when an interview AI call is not answered (no SMS / free text)."""

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


def _order_config(order: ServiceOrder) -> dict[str, Any]:
    try:
        data = json.loads(order.config_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _recipient_result(recipient: ServiceOrderRecipient) -> dict[str, Any]:
    try:
        data = json.loads(recipient.result_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def maybe_send_interview_call_retry_whatsapp(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    terminal_status: str,
) -> None:
    """Send one approved interview_email_sent WA after no_answer/busy (idempotent)."""
    if terminal_status not in {"no_answer", "busy", "failed"}:
        return
    phone = str(recipient.phone or "").strip()
    if not phone:
        return
    existing = _recipient_result(recipient)
    if existing.get("wa_retry_sent_at"):
        return

    template_row = InterviewBookingService.resolve_invite_wa_template(db, order)
    if template_row is None:
        logger.warning(
            "interview_retry_wa_skipped_no_template order=%s recipient=%s",
            order.id,
            recipient.id,
        )
        return

    cfg = _order_config(order)
    role = str(cfg.get("role") or order.title or "Interview").strip()
    company = InterviewBookingService._org_name(db, order)
    first = _first_name(recipient.name)
    careers_from = "careers@voxbulk.com"
    components = InterviewBookingService.build_email_sent_components(
        template_row,
        candidate_name=recipient.name or "Candidate",
        role=role,
        company_name=company,
        careers_email=careers_from,
    )
    log_body = f"[template:{template_row.name}] missed_call_retry candidate={first}"
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
            "wa_retry_attempted_at": datetime.utcnow().isoformat(),
            "wa_retry_template": template_row.name,
            "wa_retry_channel": result.channel if result.ok else None,
            "wa_retry_status": result.status,
            "wa_retry_detail": result.detail,
            "wa_retry_ok": result.ok,
        }
    )
    if result.ok:
        merged["wa_retry_sent_at"] = datetime.utcnow().isoformat()
        TelnyxMessagingService.log_outbound(
            db,
            org_id=order.org_id,
            to_number=phone,
            from_number=None,
            body=log_body,
            result=result,
        )
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    db.add(recipient)
    db.commit()
