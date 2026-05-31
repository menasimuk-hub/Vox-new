"""Per-candidate interview activity timeline for dashboard and admin APIs."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.interview_booking_token import InterviewBookingToken
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.interview_booking_service import booking_url_for_token, interview_booking_locked


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _event(at: str | None, *, code: str, label: str, detail: str | None = None) -> dict[str, Any] | None:
    if not at:
        return None
    return {"at": at, "code": code, "label": label, "detail": detail}


def _cancel_detail(parsed: dict[str, Any]) -> str | None:
    slot = parsed.get("cancelled_booked_start_at")
    via = str(parsed.get("booking_cancelled_via") or "").strip().lower()
    parts: list[str] = []
    if slot:
        parts.append(str(slot))
    if via:
        parts.append(f"via {via}")
    return " · ".join(parts) if parts else None


def _call_started_at(parsed: dict[str, Any]) -> str | None:
    raw = parsed.get("call_started_at") or parsed.get("started_at")
    return str(raw).strip() if raw else None


def _call_completed_at(parsed: dict[str, Any]) -> str | None:
    raw = parsed.get("call_completed_at") or parsed.get("ended_at")
    return str(raw).strip() if raw else None


class InterviewActivityService:
    @staticmethod
    def activity_status(recipient: ServiceOrderRecipient, *, parsed: dict[str, Any] | None = None) -> str:
        data = parsed if parsed is not None else _loads(recipient.result_json)
        status = str(recipient.status or "pending").lower()

        if data.get("scheduling_url_sent_at") or data.get("scheduling_sent_at"):
            return "scheduling_sent"
        if data.get("analysis_saved_at") or (isinstance(data.get("analysis"), dict) and data["analysis"].get("score") is not None):
            if status in {"completed", "done"}:
                return "report_ready"
        if status in {"calling", "in_progress", "ringing"}:
            return "calling"
        if status in {"completed", "done"}:
            return "interview_completed"
        if status in {"failed", "no_answer", "busy", "cancelled"}:
            return "call_failed"
        if data.get("booking_cancelled_at") and not data.get("booked_start_at"):
            return "booking_cancelled"
        if data.get("booked_start_at") or data.get("booking_confirmed_at"):
            booked = data.get("booked_start_at")
            if booked:
                try:
                    start = datetime.fromisoformat(str(booked).replace("Z", "+00:00"))
                    if start > datetime.utcnow():
                        return "booked_waiting"
                except Exception:
                    pass
            return "booked"
        if data.get("invite_email_sent_at") or data.get("booking_invite_sent_at"):
            return "awaiting_booking"
        return "pending"

    @staticmethod
    def timeline(
        db: Session,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        *,
        token_row: InterviewBookingToken | None = None,
    ) -> dict[str, Any]:
        parsed = _loads(recipient.result_json)
        events: list[dict[str, Any]] = []

        for item in (
            _event(recipient.created_at.isoformat() if recipient.created_at else None, code="added", label="Added to campaign"),
            _event(parsed.get("invite_email_sent_at"), code="invite_email", label="Booking email sent", detail="careers@voxbulk.com"),
            _event(parsed.get("invite_wa_sent_at"), code="invite_wa", label="WhatsApp email notice sent"),
            _event(parsed.get("booking_invite_sent_at"), code="invite_sent", label="Invites dispatched"),
            _event(parsed.get("booking_confirmed_at"), code="booked", label="Interview slot booked", detail=parsed.get("booked_start_at")),
            _event(
                parsed.get("confirmation_email_sent_at"),
                code="confirm_email",
                label="Booking confirmation email sent",
                detail="careers@voxbulk.com",
            ),
            _event(
                parsed.get("booking_rescheduled_at"),
                code="rescheduled",
                label="Interview rescheduled",
                detail=parsed.get("previous_booked_start_at"),
            ),
            _event(
                parsed.get("booking_cancelled_at"),
                code="cancelled",
                label="Interview booking cancelled",
                detail=_cancel_detail(parsed),
            ),
            _event(
                parsed.get("cancellation_email_sent_at"),
                code="cancel_email",
                label="Cancellation email sent",
                detail="careers@voxbulk.com",
            ),
            _event(_call_started_at(parsed), code="calling", label="AI call started"),
            _event(_call_completed_at(parsed), code="call_done", label="AI call completed"),
            _event(parsed.get("analysis_saved_at"), code="analysis", label="Interview analysed"),
            _event(parsed.get("scheduling_url_sent_at") or parsed.get("scheduling_sent_at"), code="scheduling", label="Human interview link sent"),
        ):
            if item:
                events.append(item)

        if token_row is None:
            token_row = db.execute(
                select(InterviewBookingToken)
                .where(
                    InterviewBookingToken.order_id == order.id,
                    InterviewBookingToken.recipient_id == recipient.id,
                )
                .order_by(InterviewBookingToken.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()

        book_url = parsed.get("booking_url")
        if not book_url and token_row and not interview_booking_locked(recipient):
            book_url = booking_url_for_token(token_row.token)
        if interview_booking_locked(recipient):
            book_url = None

        return {
            "recipient_id": recipient.id,
            "name": recipient.name,
            "email": recipient.email,
            "phone": recipient.phone,
            "status": recipient.status,
            "activity_status": InterviewActivityService.activity_status(recipient, parsed=parsed),
            "booked_start_at": parsed.get("booked_start_at"),
            "booked_end_at": parsed.get("booked_end_at"),
            "booking_url": book_url,
            "events": sorted(events, key=lambda e: str(e.get("at") or "")),
        }
