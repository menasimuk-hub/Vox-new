"""Handle WhatsApp quick-reply taps for interview booking (Reschedule / Cancel / Book)."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.interview_booking_token import InterviewBookingToken
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.interview_booking_service import (
    InterviewBookingService,
    _format_slot_date,
    _format_slot_time,
    booking_reschedule_url_for_token,
    booking_url_for_token,
    interview_booking_locked,
)
from app.services.messaging_log_service import normalize_e164
from app.services.telnyx_messaging_service import TelnyxMessagingService

logger = logging.getLogger(__name__)

_CANCEL_RE = re.compile(r"(?:❌\s*)?cancel(?:led|lation)?(?:\s+interview|\s+my\s+interview|\s+please|\s+it)?\s*$", re.I)
_CANCEL_FREE_RE = re.compile(
    r"(?:can'?t|cannot|won'?t)\s+(?:make|attend|do)\s+(?:it|the\s+interview)?|"
    r"need\s+to\s+cancel|"
    r"please\s+cancel|"
    r"^cancel(?:led)?$",
    re.I,
)
_RESCHEDULE_RE = re.compile(r"(?:🔄\s*)?reschedule(?:\s+interview|\s+please)?\s*$", re.I)
_RESCHEDULE_FREE_RE = re.compile(
    r"(?:change|move|pick)\s+(?:my\s+)?(?:time|slot|interview)|"
    r"need\s+to\s+reschedule|"
    r"different\s+time",
    re.I,
)
_BOOK_RE = re.compile(r"(?:📅\s*)?book(?:\s+my)?\s+interview\s*$", re.I)
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)


def _looks_like_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(str(value or "").strip()))


def _iter_template_button_labels(components: Any) -> list[tuple[str, str]]:
    if not isinstance(components, list):
        return []
    out: list[tuple[str, str]] = []
    for comp in components:
        if str(comp.get("type") or "").upper() != "BUTTONS":
            continue
        for btn in comp.get("buttons") or []:
            if not isinstance(btn, dict):
                continue
            label = str(
                btn.get("text") or btn.get("title") or btn.get("label") or btn.get("button_text") or ""
            ).strip()
            if not label:
                continue
            button_id = str(btn.get("id") or btn.get("payload") or "").strip()
            out.append((button_id, label))
    return out


def resolve_button_label_from_templates(db: Session, button_id: str) -> str | None:
    clean_id = str(button_id or "").strip()
    if not clean_id:
        return None
    from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate

    rows = list(db.execute(select(TelnyxWhatsappTemplate)).scalars())
    for row in rows:
        try:
            import json as _json

            components = _json.loads(row.components_json or "null")
        except Exception:
            components = None
        if not isinstance(components, list):
            continue
        for bid, label in _iter_template_button_labels(components):
            if bid and bid == clean_id:
                return label
    return None


def resolve_intent_from_order_templates(db: Session, button_id: str, order: ServiceOrder) -> str | None:
    clean_id = str(button_id or "").strip()
    if not clean_id:
        return None
    from app.services.interview_booking_service import InterviewBookingService, _template_components

    template_rows = [
        InterviewBookingService.resolve_confirmation_template(db, order),
        InterviewBookingService.resolve_invite_wa_template(db, order),
        InterviewBookingService.resolve_template(db, order),
    ]
    for row in template_rows:
        if row is None:
            continue
        for bid, label in _iter_template_button_labels(_template_components(row)):
            if bid == clean_id:
                intent = parse_interview_booking_intent(label)
                if intent:
                    return intent
    return None


def resolve_interview_booking_intent(
    db: Session,
    *,
    body: str,
    button_id: str = "",
    button_title: str = "",
    org_id: str | None = None,
    order: ServiceOrder | None = None,
) -> str | None:
    for candidate in (button_title, body):
        intent = parse_interview_booking_intent(candidate)
        if intent:
            return intent

    clean_id = str(button_id or "").strip()
    if not clean_id and _looks_like_uuid(body):
        clean_id = str(body).strip()
    if not clean_id:
        return None

    label = resolve_button_label_from_templates(db, clean_id)
    if label:
        intent = parse_interview_booking_intent(label)
        if intent:
            return intent

    if order is not None:
        return resolve_intent_from_order_templates(db, clean_id, order)

    return None

def parse_interview_booking_intent(body: str) -> str | None:
    text = re.sub(r"[\u200b-\u200d\ufeff]", "", str(body or "")).strip()
    if not text:
        return None
    compact = re.sub(r"\s+", " ", text).strip().lower()
    compact_no_emoji = re.sub(r"[^\w\s]", "", compact).strip()
    if compact in {"cancel", "❌ cancel", "cancel interview", "cancel booking", "cancelled", "🛑 cancel"}:
        return "cancel"
    if compact_no_emoji in {"cancel", "cancelled", "cancel interview", "cancel booking"}:
        return "cancel"
    if re.search(r"\bcancel\b", compact_no_emoji) and "reschedule" not in compact_no_emoji:
        return "cancel"
    if compact in {"reschedule", "🔄 reschedule", "reschedule interview", "reschedule booking"}:
        return "reschedule"
    if compact in {"book my interview", "📅 book my interview", "book interview"}:
        return "book"
    if _CANCEL_RE.search(text) or _CANCEL_FREE_RE.search(text):
        return "cancel"
    if "cancel" in compact and "reschedule" not in compact and len(compact) <= 32:
        return "cancel"
    if _RESCHEDULE_RE.search(text) or _RESCHEDULE_FREE_RE.search(text):
        return "reschedule"
    if _BOOK_RE.search(text):
        return "book"
    return None


def _phone_candidates(phone: str) -> set[str]:
    out: set[str] = set()
    raw = str(phone or "").strip()
    if not raw:
        return out
    out.add(raw)
    try:
        out.add(normalize_e164(raw))
    except ValueError:
        pass
    digits = re.sub(r"\D", "", raw)
    if digits:
        out.add(digits)
        if len(digits) >= 10:
            out.add(digits[-10:])
    return {p for p in out if p}


def find_active_booking_context(
    db: Session,
    *,
    from_phone: str,
    org_id: str | None = None,
) -> tuple[InterviewBookingToken, ServiceOrder, ServiceOrderRecipient] | None:
    needles = _phone_candidates(from_phone)
    if not needles:
        return None

    rows = list(
        db.execute(
            select(InterviewBookingToken, ServiceOrder, ServiceOrderRecipient)
            .join(ServiceOrder, ServiceOrder.id == InterviewBookingToken.order_id)
            .join(ServiceOrderRecipient, ServiceOrderRecipient.id == InterviewBookingToken.recipient_id)
            .where(
                ServiceOrder.service_code == "interview",
                ServiceOrder.status.not_in(["cancelled", "draft"]),
            )
            .order_by(InterviewBookingToken.updated_at.desc())
        ).all()
    )

    now = datetime.utcnow()
    matches: list[tuple[InterviewBookingToken, ServiceOrder, ServiceOrderRecipient, int]] = []
    for token_row, order, recipient in rows:
        rec_phones = _phone_candidates(recipient.phone or "")
        if not needles.intersection(rec_phones):
            continue
        if token_row.expires_at and now > token_row.expires_at and token_row.booked_start_at is None:
            continue
        if interview_booking_locked(recipient):
            continue
        merged = {}
        try:
            import json as _json

            merged = _json.loads(recipient.result_json or "{}")
            if not isinstance(merged, dict):
                merged = {}
        except Exception:
            merged = {}
        has_context = (
            token_row.booked_start_at is not None
            or token_row.wa_sent_at is not None
            or merged.get("invite_wa_sent_at")
            or merged.get("booking_confirmed_at")
            or merged.get("booked_start_at")
        )
        if not has_context:
            continue
        priority = 0
        if token_row.booked_start_at is not None:
            priority += 10
        if merged.get("booking_confirmed_at") or merged.get("booked_start_at"):
            priority += 5
        matches.append((token_row, order, recipient, priority))

    if not matches:
        return None

    matches.sort(key=lambda item: item[3], reverse=True)
    if org_id:
        for token_row, order, recipient, _priority in matches:
            if order.org_id == org_id:
                return token_row, order, recipient
    return matches[0][0], matches[0][1], matches[0][2]


def _send_text_reply(
    db: Session,
    *,
    org_id: str,
    to_number: str,
    body: str,
) -> bool:
    result = TelnyxMessagingService.send_whatsapp(
        db,
        to_number=to_number,
        body=body,
        org_id=org_id,
    )
    try:
        TelnyxMessagingService.log_outbound(
            db,
            org_id=org_id,
            to_number=to_number,
            from_number=None,
            body=body,
            result=result,
        )
    except Exception:
        pass
    return bool(result.ok)


def handle_inbound_reply(
    db: Session,
    *,
    from_phone: str,
    body: str,
    button_id: str = "",
    button_title: str = "",
    org_id: str | None = None,
    log_id: str | int | None = None,
) -> dict[str, Any]:
    ctx = find_active_booking_context(db, from_phone=from_phone, org_id=org_id)
    order = ctx[1] if ctx else None
    intent = resolve_interview_booking_intent(
        db,
        body=body,
        button_id=button_id,
        button_title=button_title,
        org_id=org_id,
        order=order,
    )
    if not intent and ctx is not None:
        clean_id = str(button_id or "").strip() or (str(body).strip() if _looks_like_uuid(body) else "")
        if clean_id:
            intent = resolve_intent_from_order_templates(db, clean_id, ctx[1])
    if not intent:
        return {"handled": False, "reason": "no_matching_intent", "button_id": button_id, "body": body[:120]}

    if ctx is None:
        return {"handled": False, "reason": "no_active_booking", "intent": intent}

    token_row, order, recipient = ctx
    if not recipient.phone:
        return {"handled": False, "reason": "no_recipient_phone"}

    first = str(recipient.name or "there").strip().split()[0] or "there"
    book_url = booking_url_for_token(token_row.token)
    reschedule_url = booking_reschedule_url_for_token(token_row.token)

    try:
        if intent == "cancel":
            if token_row.booked_start_at is None:
                msg = (
                    f"Hi {first}, you don't have a booked interview to cancel yet. "
                    f"Choose a time here: {book_url}"
                )
                sent = _send_text_reply(db, org_id=order.org_id, to_number=recipient.phone, body=msg)
                return {"handled": True, "action": "cancel_none_booked", "sent": sent, "log_id": log_id}

            slot = token_row.booked_start_at
            InterviewBookingService.cancel_booking(db, token_row.token, source="whatsapp")
            when = f"{_format_slot_date(slot)} at {_format_slot_time(slot)}"
            msg = (
                f"Hi {first}, your interview on {when} has been cancelled. "
                f"You can book again anytime: {book_url}"
            )
            sent = _send_text_reply(db, org_id=order.org_id, to_number=recipient.phone, body=msg)
            return {"handled": True, "action": "cancelled", "sent": sent, "log_id": log_id}

        if intent == "reschedule":
            if token_row.booked_start_at is not None:
                slot = token_row.booked_start_at
                when = f"{_format_slot_date(slot)} at {_format_slot_time(slot)}"
                msg = (
                    f"Hi {first}, your interview is currently booked for {when}. "
                    f"Tap here to pick a new time: {reschedule_url}"
                )
            else:
                msg = f"Hi {first}, pick your interview time here: {book_url}"
            sent = _send_text_reply(db, org_id=order.org_id, to_number=recipient.phone, body=msg)
            return {"handled": True, "action": "reschedule_link", "sent": sent, "log_id": log_id}

        msg = f"Hi {first}, book your interview here: {book_url}"
        sent = _send_text_reply(db, org_id=order.org_id, to_number=recipient.phone, body=msg)
        return {"handled": True, "action": "book_link", "sent": sent, "log_id": log_id}

    except ValueError as exc:
        logger.warning(
            "interview_wa_inbound_failed",
            extra={"intent": intent, "token": token_row.token, "error": str(exc)},
        )
        err_msg = f"Hi {first}, we couldn't update your booking ({exc}). Please try again: {book_url}"
        sent = _send_text_reply(db, org_id=order.org_id, to_number=recipient.phone, body=err_msg)
        return {"handled": True, "action": "error_reply", "error": str(exc), "sent": sent, "log_id": log_id}
    except Exception as exc:
        logger.exception(
            "interview_wa_inbound_unexpected",
            extra={"intent": intent, "token": token_row.token},
        )
        return {"handled": False, "reason": "handler_error", "error": str(exc), "log_id": log_id}
