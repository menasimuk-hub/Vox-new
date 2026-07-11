"""Browser meeting room (Telnyx WebRTC + AI assistant) for interview candidates."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.meeting_room_languages import meeting_room_language_label
from app.models.interview_booking_token import InterviewBookingToken
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.interview_booking_service import (
    interview_slot_minutes,
    meeting_url_for_token,
)
from app.services.interview_voice_agent_service import (
    build_interview_opening_greeting,
    build_interview_runtime_instructions,
    resolve_interview_telnyx_assistant_id,
)
from app.services.platform_catalog_service import ServiceOrderService
from app.services.telnyx_assistant_service import prepare_telnyx_webrtc_call

logger = logging.getLogger(__name__)

MEETING_CHANNEL = "meeting"
PHONE_CHANNEL = "phone"

# Candidate can connect to the paid Telnyx room at most this many seconds before
# the booked slot. Before that they sit in the (free) waiting area.
MEETING_EARLY_JOIN_SECONDS = 60


def _recipient_result(recipient: ServiceOrderRecipient) -> dict[str, Any]:
    try:
        data = json.loads(recipient.result_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _set_recipient_result(db: Session, recipient: ServiceOrderRecipient, payload: dict[str, Any]) -> dict[str, Any]:
    merged = _recipient_result(recipient)
    merged.update(payload)
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    db.add(recipient)
    db.commit()
    db.refresh(recipient)
    return merged


def _booking_row(db: Session, token: str) -> tuple[InterviewBookingToken, ServiceOrder, ServiceOrderRecipient]:
    row = db.execute(
        select(InterviewBookingToken).where(InterviewBookingToken.token == str(token).strip()).limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise ValueError("Meeting link not found or expired")
    order = db.get(ServiceOrder, row.order_id)
    recipient = db.get(ServiceOrderRecipient, row.recipient_id)
    if order is None or recipient is None:
        raise ValueError("Meeting link is no longer valid")
    return row, order, recipient


def _assert_meeting_slot_window(
    db: Session,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    row: InterviewBookingToken,
    *,
    now: datetime | None = None,
) -> None:
    now = now or datetime.utcnow()
    config = {}
    try:
        config = json.loads(order.config_json or "{}")
        if not isinstance(config, dict):
            config = {}
    except Exception:
        config = {}
    booking_required = bool(config.get("require_booking", True))

    # NOTE: do not reuse _recipient_eligible_for_dial here — that helper is for
    # PHONE dialing and deliberately rejects meeting-channel bookings, which
    # would block every web candidate. Meeting eligibility is purely about the
    # booked time window (and the booking not having been cancelled).
    merged = _recipient_result(recipient)
    if merged.get("booking_withdrawn") or merged.get("booking_cancelled_at"):
        raise ValueError("This interview booking was cancelled — contact the employer to rebook")

    if not booking_required:
        return

    slot_start = row.booked_start_at
    if slot_start is None:
        raise ValueError("Please book a time slot before joining the meeting")

    slot_end = slot_start + timedelta(minutes=interview_slot_minutes())
    grace_end = slot_end + timedelta(minutes=15)
    if now < slot_start - timedelta(seconds=MEETING_EARLY_JOIN_SECONDS):
        raise ValueError("Your interview room opens 1 minute before your booked time — please wait")
    if now > grace_end:
        raise ValueError("Your booked interview slot has passed — contact the employer to reschedule")


def _language_instruction_suffix(language_code: str) -> str:
    label = meeting_room_language_label(language_code)
    return (
        f"\n\nConduct this interview in {label}. "
        f"Speak and listen in {label} unless the candidate clearly prefers another language."
    )


def _meeting_custom_headers(order: ServiceOrder, recipient: ServiceOrderRecipient) -> list[dict[str, str]]:
    """Telnyx WebRTC requires ``[{name, value}]`` SIP headers (same as front-page call leads)."""
    headers: list[dict[str, str]] = [
        {"name": "X-Interview-Recipient-Id", "value": str(recipient.id)},
        {"name": "X-Service-Order-Id", "value": str(order.id)},
        {"name": "X-Interview-Order-Id", "value": str(order.id)},
    ]
    return [row for row in headers if str(row.get("value") or "").strip()]


class InterviewMeetingService:
    @staticmethod
    def start_meeting(db: Session, token: str) -> dict[str, Any]:
        row, order, recipient = _booking_row(db, token)
        if str(row.channel or "").strip().lower() != MEETING_CHANNEL:
            raise ValueError("This booking is not set up for an online meeting")

        _assert_meeting_slot_window(db, order, recipient, row)

        config = {}
        try:
            config = json.loads(order.config_json or "{}")
            if not isinstance(config, dict):
                config = {}
        except Exception:
            config = {}

        from app.services.voice_agent_runtime import (
            InterviewAgentLanguageMismatch,
            detect_interview_language,
            resolve_interview_language,
        )

        assistant_id, agent = resolve_interview_telnyx_assistant_id(db, order, config)
        if not assistant_id:
            raise ValueError("Interview AI agent is not configured")

        try:
            effective_language = detect_interview_language(config, agent)
        except InterviewAgentLanguageMismatch as exc:
            raise ValueError(str(exc)) from exc
        # Meeting chrome follows the interview language only (not platform meeting-room default).
        if effective_language not in {"ar", "en"}:
            effective_language = resolve_interview_language(config)

        instructions = build_interview_runtime_instructions(
            db,
            order=order,
            config=config,
            recipient=recipient,
            agent=agent,
        )
        instructions = f"{instructions}{_language_instruction_suffix(effective_language)}"

        greeting = build_interview_opening_greeting(
            db,
            agent=agent,
            config=config,
            recipient_name=str(recipient.name or "there"),
            org_id=order.org_id,
            order=order,
        )

        from app.services.telnyx_assistant_service import apply_interview_assistant_pacing

        try:
            apply_interview_assistant_pacing(db, assistant_id)
        except Exception:
            pass

        prep = prepare_telnyx_webrtc_call(
            db, assistant_id, instructions, greeting=greeting or None, language=effective_language
        )

        custom_headers = _meeting_custom_headers(order, recipient)

        now = datetime.utcnow()
        _set_recipient_result(
            db,
            recipient,
            {
                "channel": MEETING_CHANNEL,
                "transport": "webrtc",
                "meeting_started_at": now.isoformat(),
                "meeting_url": meeting_url_for_token(row.token),
                "telnyx_assistant_id": prep.get("assistant_id") or assistant_id,
                "interview_language_code": effective_language,
            },
        )

        if str(recipient.status or "").lower() not in {"completed", "done", "calling"}:
            recipient.status = "calling"
            recipient.updated_at = now
            db.add(recipient)
            db.commit()
            db.refresh(recipient)

        return {
            "ok": True,
            "agent_id": prep.get("assistant_id") or assistant_id,
            "greeting": greeting,
            "custom_headers": custom_headers,
            "web_calls_enabled": bool(prep.get("web_calls_enabled")),
            "meeting_url": meeting_url_for_token(row.token),
            "candidate_name": recipient.name,
            "role": str(config.get("role") or config.get("position") or order.title or "Interview"),
            "interview_language": "ar" if effective_language == "ar" else "en",
        }

    @staticmethod
    def complete_meeting(
        db: Session,
        token: str,
        *,
        duration_seconds: int | None = None,
        provider_call_id: str | None = None,
    ) -> dict[str, Any]:
        row, order, recipient = _booking_row(db, token)
        now = datetime.utcnow()

        merged = _recipient_result(recipient)
        started_at = merged.get("meeting_started_at")
        secs = duration_seconds
        if secs is None and started_at:
            try:
                start_dt = datetime.fromisoformat(str(started_at).replace("Z", "+00:00")).replace(tzinfo=None)
                secs = max(1, int((now - start_dt).total_seconds()))
            except Exception:
                secs = None

        from app.services.billing_call_minutes import billable_call_minutes

        payload: dict[str, Any] = {
            "channel": MEETING_CHANNEL,
            "transport": "webrtc",
            "ended_at": now.isoformat(),
            "meeting_ended_at": now.isoformat(),
            "call_channel": MEETING_CHANNEL,
        }
        if provider_call_id:
            payload["telnyx_conversation_id"] = str(provider_call_id).strip()
            payload["provider_call_id"] = str(provider_call_id).strip()
        if secs is not None:
            payload["duration_seconds"] = int(secs)
            payload["billable_minutes"] = billable_call_minutes(int(secs))

        _set_recipient_result(db, recipient, payload)
        db.refresh(recipient)

        recipient.status = "completed"
        recipient.updated_at = now
        db.add(recipient)
        db.commit()

        from app.services.interview_analysis_service import InterviewAnalysisService

        InterviewAnalysisService.process_recipient_post_call(
            db,
            order=order,
            recipient=recipient,
            terminal_status="completed",
            hangup_extra={"duration_seconds": secs},
        )

        from app.services.interview_call_dispatch_service import _finalize_order_if_done

        db.refresh(order)
        db.refresh(recipient)
        _finalize_order_if_done(db, order)

        try:
            from app.services.interview_missed_call_email_service import (
                maybe_send_interview_thank_you_email,
            )

            maybe_send_interview_thank_you_email(db, order=order, recipient=recipient)
        except Exception:
            logger.exception("interview_meeting_thank_you_email_failed")

        schedule_interview_meeting_analysis_retry(db, order.id, recipient.id)

        return {"ok": True, "status": recipient.status}


def schedule_interview_meeting_analysis_retry(db: Session, order_id: str, recipient_id: str) -> None:
    """Daemon retry when Telnyx transcript is not ready immediately after WebRTC hangup."""
    import threading
    import time

    from app.core.database import get_sessionmaker

    def _worker() -> None:
        sessionmaker = get_sessionmaker()
        for delay in (5, 15, 30, 60, 120, 240):
            time.sleep(delay)
            try:
                with sessionmaker() as session:
                    order = session.get(ServiceOrder, order_id)
                    recipient = session.get(ServiceOrderRecipient, recipient_id)
                    if not order or not recipient:
                        return
                    from app.services.interview_analysis_service import InterviewAnalysisService
                    from app.services.survey_analysis_service import ensure_survey_transcript

                    ensure_survey_transcript(session, order=order, recipient=recipient)
                    session.refresh(recipient)
                    InterviewAnalysisService.run_interview_analysis_if_needed(
                        session, order=order, recipient=recipient
                    )
                    merged = _recipient_result(recipient)
                    if merged.get("analysis_saved_at"):
                        return
            except Exception:
                logger.exception("meeting_analysis_retry_failed order=%s recipient=%s", order_id, recipient_id)

    threading.Thread(target=_worker, daemon=True).start()
