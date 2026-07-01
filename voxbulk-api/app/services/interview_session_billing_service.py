"""Interview session billing — web meetings and phone calls share the same retail rates and usage metering."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.billing_call_minutes import billable_call_minutes


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _config_delivery(order_config: dict[str, Any] | None) -> str:
    cfg = order_config if isinstance(order_config, dict) else {}
    return str(cfg.get("delivery") or cfg.get("delivery_mode") or "").strip().lower()


def recipient_session_kind(
    result: dict[str, Any],
    *,
    config_delivery: str | None = None,
) -> str:
    """web_meeting | phone_call | session_unknown | no_session"""
    ch = str(result.get("channel") or result.get("call_channel") or "").lower()
    tr = str(result.get("transport") or "").lower()
    if tr == "webrtc" or ch in {"meeting", "ai_meeting"}:
        return "web_meeting"
    if result.get("call_control_id") or ch in {"ai_call", "phone", "call"}:
        return "phone_call"
    delivery = str(config_delivery or "").lower()
    if result.get("duration_seconds") or result.get("meeting_started_at") or result.get("meeting_ended_at"):
        if delivery == "ai_meeting":
            return "web_meeting"
        if delivery == "ai_call":
            return "phone_call"
        return "session_unknown"
    if delivery == "ai_meeting" and (
        result.get("booking_token") or result.get("meeting_url") or result.get("meeting_started_at")
    ):
        return "web_meeting"
    return "no_session"


def summarize_interview_sessions(
    recipients: list[ServiceOrderRecipient],
    *,
    order_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    delivery = _config_delivery(order_config)
    web = phone = unknown = none = 0
    billable_minutes = 0
    for recipient in recipients:
        result = _loads(recipient.result_json)
        kind = recipient_session_kind(result, config_delivery=delivery)
        if kind == "web_meeting":
            web += 1
        elif kind == "phone_call":
            phone += 1
        elif kind == "session_unknown":
            unknown += 1
        else:
            none += 1
        try:
            bm = int(result.get("billable_minutes") or 0)
        except (TypeError, ValueError):
            bm = 0
        if bm <= 0:
            bm = billable_call_minutes(result.get("duration_seconds"))
        billable_minutes += max(0, bm)

    if web > 0 and phone > 0:
        interview_format = "mixed"
        format_label = "Phone + web"
    elif web > 0:
        interview_format = "web"
        format_label = "Web interview"
    elif phone > 0 or (unknown > 0 and delivery != "ai_meeting"):
        interview_format = "phone"
        format_label = "Phone AI"
    elif unknown > 0 and delivery == "ai_meeting":
        interview_format = "web"
        format_label = "Web interview"
    elif delivery == "ai_meeting":
        interview_format = "web"
        format_label = "Web interview"
    else:
        interview_format = "none"
        format_label = "No sessions yet"

    return {
        "web_sessions": web,
        "phone_sessions": phone,
        "unknown_sessions": unknown,
        "no_session": none,
        "total_billable_minutes": billable_minutes,
        "interview_format": interview_format,
        "interview_format_label": format_label,
    }


def is_voice_billing_channel(channel: str) -> bool:
    return str(channel or "").lower() in {
        "ai_call",
        "ai_meeting",
        "phone",
        "call",
        "meeting",
    }


def _billable_minutes_for_recipient(result: dict[str, Any]) -> int:
    try:
        bm = int(result.get("billable_minutes") or 0)
    except (TypeError, ValueError):
        bm = 0
    if bm > 0:
        return bm
    return billable_call_minutes(result.get("duration_seconds"))


def _merge_recipient_result(db: Session, recipient: ServiceOrderRecipient, patch: dict[str, Any]) -> None:
    merged = _loads(recipient.result_json)
    merged.update(patch)
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    recipient.updated_at = datetime.utcnow()
    db.add(recipient)


def meter_session_if_needed(db: Session, order: ServiceOrder, recipient: ServiceOrderRecipient) -> int:
    """Record plan usage for one completed interview session (web or phone). Idempotent."""
    if order.service_code != "interview":
        return 0
    db.refresh(recipient)
    result = _loads(recipient.result_json)
    if result.get("usage_metered_at"):
        return int(result.get("usage_metered_minutes") or 0)
    bm = _billable_minutes_for_recipient(result)
    if bm <= 0:
        return 0
    try:
        from app.services.usage_wallet_service import UsageWalletService

        UsageWalletService.record_call_usage(db, org_id=order.org_id, units=bm)
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "interview_session_usage_meter_failed order_id=%s recipient_id=%s",
            order.id,
            recipient.id,
        )
        return 0
    _merge_recipient_result(
        db,
        recipient,
        {
            "usage_metered_at": datetime.utcnow().isoformat(),
            "usage_metered_minutes": bm,
        },
    )
    db.commit()
    db.refresh(recipient)
    return bm


def unmetered_billable_minutes(recipients: list[ServiceOrderRecipient]) -> int:
    total = 0
    for recipient in recipients:
        result = _loads(recipient.result_json)
        if result.get("usage_metered_at"):
            continue
        total += _billable_minutes_for_recipient(result)
    return total
