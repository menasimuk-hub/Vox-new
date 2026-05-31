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


def parse_interview_booking_intent(body: str) -> str | None:
    text = str(body or "").strip()
    if not text:
        return None
    if _CANCEL_RE.search(text) or _CANCEL_FREE_RE.search(text):
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
    for token_row, order, recipient in rows:
        if org_id and order.org_id != org_id:
            continue
        rec_phones = _phone_candidates(recipient.phone or "")
        if not needles.intersection(rec_phones):
            continue
        if token_row.expires_at and now > token_row.expires_at:
            continue
        if interview_booking_locked(recipient):
            continue
        if token_row.wa_sent_at is None and token_row.booked_start_at is None:
            continue
        return token_row, order, recipient
    if org_id:
        for token_row, order, recipient in rows:
            rec_phones = _phone_candidates(recipient.phone or "")
            if not needles.intersection(rec_phones):
                continue
            if token_row.expires_at and now > token_row.expires_at:
                continue
            if interview_booking_locked(recipient):
                continue
            if token_row.wa_sent_at is None and token_row.booked_start_at is None:
                continue
            return token_row, order, recipient
    return None


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
    org_id: str | None = None,
    log_id: str | int | None = None,
) -> dict[str, Any]:
    intent = parse_interview_booking_intent(body)
    if not intent:
        return {"handled": False, "reason": "no_matching_intent"}

    ctx = find_active_booking_context(db, from_phone=from_phone, org_id=org_id)
    if ctx is None:
        return {"handled": False, "reason": "no_active_booking"}

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
