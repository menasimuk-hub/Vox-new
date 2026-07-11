"""Classify and apply early interview exits (not free, wrong person, recording decline, short drop)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.interview_booking_token import InterviewBookingToken
from app.models.service_order import ServiceOrder, ServiceOrderRecipient

logger = logging.getLogger(__name__)

InterviewSessionOutcome = Literal[
    "completed",
    "reschedule",
    "recording_declined",
    "wrong_person",
    "technical_abort",
]

# Under this length, treat as early exit unless the transcript shows real Q&A progress.
EARLY_EXIT_MAX_SECONDS = 150
# At/above this, mid-interview stop stays completed (product choice A).
SUBSTANTIAL_SECONDS = 180

_RECORDING_DECLINE_RE = re.compile(
    r"(?:"
    r"don'?t\s+(?:want\s+)?(?:to\s+)?record|"
    r"do\s+not\s+record|"
    r"no\s+(?:i\s+)?(?:don'?t|do\s+not)\s+(?:consent|agree)|"
    r"not\s+okay\s+to\s+record|"
    r"refuse\s+(?:to\s+)?record|"
    r"recording\s+(?:is\s+)?not\s+okay|"
    r"لا\s+(?:موافق|أوافق|اريد|أريد).{0,20}تسجيل|"
    r"مش\s+موافق.{0,20}تسجيل|"
    r"مرفوض\s+التسجيل"
    r")",
    re.I,
)

_WRONG_PERSON_RE = re.compile(
    r"(?:"
    r"wrong\s+(?:person|number)|"
    r"you\s+have\s+the\s+wrong|"
    r"no\s+one\s+(?:by|named)\s+that|"
    r"there'?s?\s+no\s+(?:\w+\s+){0,2}here|"
    r"isn'?t?\s+(?:me|here)|"
    r"not\s+(?:me|him|her)|"
    r"رقم\s+غلط|"
    r"شخص\s+غلط|"
    r"مش\s+أنا|"
    r"لست\s+(?:أنا|انا)"
    r")",
    re.I,
)

_RESCHEDULE_RE = re.compile(
    r"(?:"
    r"not\s+(?:a\s+)?good\s+time|"
    r"not\s+free|"
    r"i'?m\s+busy|"
    r"can(?:not|\s*n'?t)?\s+talk|"
    r"call\s+(?:me\s+)?(?:back|later)|"
    r"another\s+time|"
    r"reschedul|"
    r"re-?schedule|"
    r"different\s+(?:time|day)|"
    r"later\s+(?:today|this\s+week)|"
    r"وقت\s+(?:مش|غير)\s+مناسب|"
    r"مش\s+فاضي|"
    r"غير\s+متاح|"
    r"أعد\s+الجدولة|"
    r"إعادة\s+جدولة|"
    r"موعد\s+آخر|"
    r"وقت\s+ثاني"
    r")",
    re.I,
)

_QA_PROGRESS_RE = re.compile(
    r"(?:"
    r"first\s+question|"
    r"next\s+question|"
    r"tell\s+me\s+about|"
    r"can\s+you\s+describe|"
    r"what\s+(?:is|was)\s+your\s+experience|"
    r"السؤال\s+(?:الأول|التالي)|"
    r"خبرت|خبرتك|"
    r"صف\s+لي"
    r")",
    re.I,
)


def _recipient_result(recipient: ServiceOrderRecipient) -> dict[str, Any]:
    try:
        data = json.loads(recipient.result_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _set_recipient_result(db: Session, recipient: ServiceOrderRecipient, patch: dict[str, Any]) -> None:
    merged = _recipient_result(recipient)
    merged.update(patch)
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    recipient.updated_at = datetime.utcnow()
    db.add(recipient)
    db.commit()
    db.refresh(recipient)


def _booking_token(db: Session, order_id: str, recipient_id: str) -> InterviewBookingToken | None:
    return db.execute(
        select(InterviewBookingToken).where(
            InterviewBookingToken.order_id == order_id,
            InterviewBookingToken.recipient_id == recipient_id,
        )
    ).scalar_one_or_none()


def transcript_shows_interview_progress(transcript: str | None) -> bool:
    text = str(transcript or "").strip()
    if len(text) < 220:
        return False
    if _QA_PROGRESS_RE.search(text):
        return True
    # Rough turn count: several speaker-like lines.
    lines = [ln for ln in re.split(r"[\n.]+", text) if len(ln.strip()) > 20]
    return len(lines) >= 8


def classify_interview_session_outcome(
    *,
    duration_seconds: int | None,
    transcript: str | None = None,
) -> InterviewSessionOutcome:
    """Decide whether a connected session was a finished interview or an early exit."""
    secs = int(duration_seconds) if duration_seconds is not None else None
    text = str(transcript or "").strip()

    if text and _RECORDING_DECLINE_RE.search(text):
        # Product choice B: recording decline is a hard stop (no rebook).
        return "recording_declined"

    progress = transcript_shows_interview_progress(text)
    if text and _WRONG_PERSON_RE.search(text) and not progress:
        return "wrong_person"

    substantial = (secs is not None and secs >= SUBSTANTIAL_SECONDS) or progress

    # Early "not free / reschedule" only before real interview progress (choice A for mid-call).
    if text and _RESCHEDULE_RE.search(text) and not substantial:
        return "reschedule"

    if substantial:
        return "completed"

    if secs is not None and secs < EARLY_EXIT_MAX_SECONDS:
        if secs < 75:
            return "technical_abort"
        # Ambiguous short session (often "not free" with thin STT) — unlock via reschedule.
        return "reschedule"

    return "completed"


def _clear_booking_slot(db: Session, token: InterviewBookingToken | None) -> str | None:
    if token is None or token.booked_start_at is None:
        return None
    previous = token.booked_start_at.isoformat()
    token.booked_start_at = None
    token.booked_end_at = None
    token.updated_at = datetime.utcnow()
    db.add(token)
    db.commit()
    return previous


def _send_reschedule_email(db: Session, order: ServiceOrder, recipient: ServiceOrderRecipient) -> bool:
    from app.services.career_email_service import CareerEmailService
    from app.services.interview_booking_service import (
        InterviewBookingService,
        booking_reschedule_url_for_token,
        resolve_booking_url,
    )

    email = str(recipient.email or "").strip().lower()
    if not email or "@" not in email:
        return False

    token = _booking_token(db, order.id, recipient.id)
    token_str = str(token.token) if token else ""
    if not token_str:
        return False

    role = "Interview"
    company = InterviewBookingService._org_name(db, order)
    try:
        cfg = json.loads(order.config_json or "{}")
        if isinstance(cfg, dict):
            role = str(cfg.get("role") or cfg.get("position") or role).strip() or role
            company = str(cfg.get("company_name") or company).strip() or company
    except Exception:
        pass

    book_url = resolve_booking_url(recipient, token_str)
    reschedule_url = booking_reschedule_url_for_token(token_str, recipient=recipient)
    ok, err, channel = CareerEmailService.send_booking_reschedule_link_email(
        db,
        to_email=email,
        variables={
            "candidate_name": str(recipient.name or "there").strip() or "there",
            "role": role,
            "company_name": company,
            "current_slot": "",
            "reschedule_url": reschedule_url,
            "booking_url": book_url,
        },
    )
    if ok:
        _set_recipient_result(
            db,
            recipient,
            {
                "reschedule_email_sent_at": datetime.utcnow().isoformat(),
                "reschedule_email_channel": channel,
            },
        )
        return True
    logger.warning(
        "interview_early_exit_reschedule_email_failed",
        extra={"order_id": order.id, "recipient_id": recipient.id, "error": err},
    )
    return False


def apply_interview_session_outcome(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    outcome: InterviewSessionOutcome,
    duration_seconds: int | None = None,
    transcript: str | None = None,
    channel: str = "meeting",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist outcome. Non-completed paths do not thank-you, score, or bill as a finished interview."""
    now = datetime.utcnow()
    now_iso = now.isoformat()
    token = _booking_token(db, order.id, recipient.id)
    patch: dict[str, Any] = {
        "session_outcome": outcome,
        "early_exit_at": now_iso if outcome != "completed" else None,
        "awaiting_candidate_action": outcome in {"reschedule", "technical_abort", "wrong_person"},
        "duration_seconds": duration_seconds,
        "channel": channel,
    }
    if transcript:
        patch["transcript"] = transcript
    if extra:
        patch.update(extra)

    if outcome == "completed":
        patch.pop("early_exit_at", None)
        patch["awaiting_candidate_action"] = False
        patch["ended_at"] = now_iso
        patch["call_completed_at"] = now_iso
        if channel == "meeting":
            patch["meeting_ended_at"] = now_iso
        recipient.status = "completed"
        recipient.updated_at = now
        _set_recipient_result(db, recipient, {k: v for k, v in patch.items() if v is not None})
        return {"ok": True, "status": recipient.status, "outcome": outcome}

    if outcome == "recording_declined":
        from app.services.survey_voice_agent_service import mark_recipient_opted_out

        patch["ended_at"] = now_iso
        patch["awaiting_candidate_action"] = False
        _set_recipient_result(db, recipient, patch)
        mark_recipient_opted_out(
            db,
            recipient,
            reason="recording_declined",
            source_text=(transcript or "")[:500],
        )
        db.refresh(recipient)
        return {
            "ok": True,
            "status": recipient.status,
            "outcome": outcome,
            "message": "Recording consent declined — interview closed.",
        }

    # reschedule / wrong_person / technical_abort → unlock booking (pending)
    cleared_slot: str | None = None
    if outcome == "reschedule":
        cleared_slot = _clear_booking_slot(db, token)
        if cleared_slot:
            patch["cleared_booked_start_at"] = cleared_slot
            patch["booking_cancelled_at"] = now_iso
            patch["booking_cancelled_via"] = "early_exit_reschedule"

    # Drop terminal locks so the candidate can rebook / rejoin.
    patch["ended_at"] = None
    patch.pop("call_completed_at", None)
    patch.pop("meeting_ended_at", None)
    patch.pop("analysis_saved_at", None)
    patch["early_exit_reason"] = outcome

    recipient.status = "pending"
    recipient.updated_at = now
    merged = _recipient_result(recipient)
    merged.update(patch)
    for key in ("ended_at", "call_completed_at", "meeting_ended_at", "analysis_saved_at"):
        merged.pop(key, None)
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    db.add(recipient)
    db.commit()
    db.refresh(recipient)

    email_sent = False
    if outcome == "reschedule":
        email_sent = _send_reschedule_email(db, order, recipient)

    messages = {
        "reschedule": "No problem — use the link in your email to pick a new time.",
        "wrong_person": "Sorry for the interruption — you can close this page.",
        "technical_abort": "Connection ended early — you can rejoin from your booking link if your slot is still open.",
    }
    return {
        "ok": True,
        "status": recipient.status,
        "outcome": outcome,
        "reschedule_email_sent": email_sent,
        "message": messages.get(outcome, ""),
    }
