"""WhatsApp/SMS retry when an interview AI call fails or is not answered."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.survey_dispatch_service import _first_name, _personalize
from app.services.telnyx_messaging_service import TelnyxMessagingService


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


def build_interview_retry_message(order: ServiceOrder, recipient: ServiceOrderRecipient) -> str:
    cfg = _order_config(order)
    org = str(cfg.get("organisation_name") or cfg.get("clinic_name") or "the hiring team").strip()
    role = str(cfg.get("role") or order.title or "the role").strip()
    first = _first_name(recipient.name or "there")
    return _personalize(
        (
            "Hi {first_name}, we tried to reach you for a brief {role} phone screening with {org_name}. "
            "Reply CALL when ready and we will try again, or email us if you need a different time."
        ),
        first_name=first,
        org_name=org,
        organiser=role,
    ).replace("{role}", role)


def maybe_send_interview_call_retry_whatsapp(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    terminal_status: str,
) -> None:
    """Send one WhatsApp/SMS retry notice after no_answer or busy (idempotent)."""
    if terminal_status not in {"no_answer", "busy", "failed"}:
        return
    if not str(recipient.phone or "").strip():
        return
    existing = _recipient_result(recipient)
    if existing.get("wa_retry_sent_at"):
        return

    body = build_interview_retry_message(order, recipient)
    result = TelnyxMessagingService.send_survey_message(
        db,
        org_id=order.org_id,
        to_number=str(recipient.phone),
        body=body,
        prefer_whatsapp=True,
    )
    merged = dict(existing)
    merged.update(
        {
            "wa_retry_sent_at": datetime.utcnow().isoformat(),
            "wa_retry_channel": result.channel if result.ok else None,
            "wa_retry_status": result.status,
            "wa_retry_detail": result.detail,
            "wa_retry_ok": result.ok,
        }
    )
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    db.add(recipient)
    db.commit()
