"""Per-candidate interview activity timeline for dashboard and admin APIs."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.interview_booking_token import InterviewBookingToken
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.interview_booking_service import interview_booking_locked, resolve_booking_url


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
        formatted = _slot_detail(str(slot))
        parts.append(f"Was booked for {formatted}" if formatted else str(slot))
    if via:
        parts.append(f"via {via}")
    return " · ".join(parts) if parts else None


def _slot_detail(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        from app.services.interview_booking_service import _format_slot_date, _format_slot_time

        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return f"{_format_slot_date(dt)} at {_format_slot_time(dt)}"
    except Exception:
        return str(raw).strip() or None


def _merge_token_into_parsed(parsed: dict[str, Any], token_row: InterviewBookingToken | None) -> dict[str, Any]:
    if token_row is None:
        return parsed
    merged = dict(parsed)
    if getattr(token_row, "booked_start_at", None) and not merged.get("booking_cancelled_at"):
        merged.setdefault("booked_start_at", token_row.booked_start_at.isoformat())
        if getattr(token_row, "booked_end_at", None):
            merged.setdefault("booked_end_at", token_row.booked_end_at.isoformat())
        if getattr(token_row, "updated_at", None):
            merged.setdefault("booking_confirmed_at", token_row.updated_at.isoformat())
    if getattr(token_row, "wa_sent_at", None):
        merged.setdefault("invite_wa_sent_at", token_row.wa_sent_at.isoformat())
    return merged


def _call_started_at(parsed: dict[str, Any]) -> str | None:
    transport = str(parsed.get("transport") or "").strip().lower()
    channel = str(parsed.get("channel") or "").strip().lower()
    if transport == "webrtc" or channel == "meeting":
        raw = parsed.get("meeting_started_at") or parsed.get("started_at")
    else:
        raw = parsed.get("call_started_at") or parsed.get("started_at")
    return str(raw).strip() if raw else None


def _call_completed_at(parsed: dict[str, Any]) -> str | None:
    transport = str(parsed.get("transport") or "").strip().lower()
    channel = str(parsed.get("channel") or "").strip().lower()
    if transport == "webrtc" or channel == "meeting":
        raw = parsed.get("meeting_ended_at") or parsed.get("ended_at") or parsed.get("call_completed_at")
    else:
        raw = parsed.get("call_completed_at") or parsed.get("ended_at")
    return str(raw).strip() if raw else None


def _session_channel_label(parsed: dict[str, Any]) -> str:
    transport = str(parsed.get("transport") or "").strip().lower()
    channel = str(parsed.get("channel") or "").strip().lower()
    if transport == "webrtc":
        return "webrtc"
    if channel == "meeting":
        return "meeting"
    return channel or "ai_call"


class InterviewActivityService:
    @staticmethod
    def activity_status(
        recipient: ServiceOrderRecipient,
        *,
        parsed: dict[str, Any] | None = None,
        order: ServiceOrder | None = None,
    ) -> str:
        data = parsed if parsed is not None else _loads(recipient.result_json)
        if data.get("cv_exclusion_keyword") and not data.get("cv_ats_reject"):
            return "auto_excluded"
        if data.get("cv_ats_reject"):
            if order is not None and str(recipient.ats_status or "").lower() == "complete" and recipient.ats_score is not None:
                from app.services.interview_cv_exclusion_service import cv_min_ats_score_from_config
                from app.services.interview_cv_email_service import _loads_config

                min_score = cv_min_ats_score_from_config(_loads_config(order))
                if int(recipient.ats_score) >= min_score:
                    pass
                else:
                    return "auto_excluded"
            else:
                return "auto_excluded"
        elif data.get("auto_excluded_at"):
            return "auto_excluded"
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
        if data.get("booking_cancelled_at") and not data.get("booked_start_at"):
            return "booking_cancelled"
        if data.get("booking_withdrawn"):
            return "booking_cancelled"
        if str(recipient.status or "").lower() == "cancelled" and not data.get("booked_start_at"):
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
        if status in {"failed", "no_answer", "busy", "skipped", "cancelled", "opted_out"}:
            if data.get("booking_cancelled_at") or data.get("booking_withdrawn") or status == "cancelled":
                return "booking_cancelled"
            return "call_failed"
        if data.get("invite_email_sent_at"):
            return "booking_email_sent"
        if data.get("invite_wa_sent_at") or data.get("booking_invite_sent_at"):
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

        if token_row is None:
            token_row = db.execute(
                select(InterviewBookingToken)
                .where(
                    InterviewBookingToken.order_id == order.id,
                    InterviewBookingToken.recipient_id == recipient.id,
                )
                .order_by(InterviewBookingToken.updated_at.desc())
                .limit(1)
            ).scalar_one_or_none()

        parsed = _merge_token_into_parsed(parsed, token_row)
        events: list[dict[str, Any]] = []

        for item in (
            _event(recipient.created_at.isoformat() if recipient.created_at else None, code="added", label="Added to campaign"),
            _event(parsed.get("invite_email_sent_at"), code="invite_email", label="Appointment booking email sent", detail="careers@voxbulk.com"),
            _event(parsed.get("invite_wa_sent_at"), code="invite_wa", label="WhatsApp booking notice sent"),
            _event(parsed.get("booking_invite_sent_at"), code="invite_sent", label="Booking invites dispatched"),
            _event(
                parsed.get("booking_confirmed_at") or parsed.get("booked_start_at"),
                code="booked",
                label="Appointment booked",
                detail=_slot_detail(parsed.get("booked_start_at")),
            ),
            _event(
                parsed.get("confirmation_email_sent_at"),
                code="confirm_email",
                label="Appointment confirmation email sent",
                detail="careers@voxbulk.com",
            ),
            _event(parsed.get("confirmation_wa_sent_at"), code="confirm_wa", label="Appointment confirmation WhatsApp sent"),
            _event(
                parsed.get("reschedule_email_sent_at"),
                code="reschedule_email",
                label="Reschedule link email sent",
                detail="careers@voxbulk.com",
            ),
            _event(
                parsed.get("booking_rescheduled_at"),
                code="rescheduled",
                label="Appointment rescheduled",
                detail=_slot_detail(parsed.get("previous_booked_start_at")),
            ),
            _event(
                parsed.get("booking_cancelled_at"),
                code="cancelled",
                label="Appointment cancelled",
                detail=_cancel_detail(parsed),
            ),
            _event(
                parsed.get("cancellation_email_sent_at"),
                code="cancel_email",
                label="Appointment cancellation email sent",
                detail="careers@voxbulk.com",
            ),
            _event(
                parsed.get("ats_scanned_at") or parsed.get("ats_completed_at"),
                code="ats_scan",
                label="CV / ATS screening completed",
                detail=(
                    f"Score {recipient.ats_score}"
                    if recipient.ats_score is not None
                    else str(recipient.ats_status or "").strip() or None
                ),
            ),
            _event(
                _call_started_at(parsed),
                code="calling",
                label=(
                    "Web interview started"
                    if _session_channel_label(parsed) in {"meeting", "webrtc"}
                    else "AI interview call started"
                ),
            ),
            _event(
                _call_completed_at(parsed),
                code="call_done",
                label=(
                    "Web interview completed"
                    if _session_channel_label(parsed) in {"meeting", "webrtc"}
                    else "AI interview call completed"
                ),
            ),
            _event(parsed.get("analysis_saved_at"), code="analysis", label="Interview report ready"),
            _event(parsed.get("scheduling_url_sent_at") or parsed.get("scheduling_sent_at"), code="scheduling", label="Human interview link sent"),
        ):
            if item:
                events.append(item)

        book_url = None
        if token_row and not interview_booking_locked(recipient):
            book_url = resolve_booking_url(recipient, token_row.token)
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
