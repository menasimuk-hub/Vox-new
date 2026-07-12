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
    r"can(?:not|\s*n'?t)?\s+continue|"
    r"have\s+to\s+(?:go|stop|leave)|"
    r"need\s+to\s+(?:go|stop|leave|reschedule)|"
    r"stop\s+the\s+(?:call|interview)|"
    r"end\s+the\s+(?:call|interview)|"
    r"call\s+(?:me\s+)?(?:back|later)|"
    r"another\s+time|"
    r"reschedul|"
    r"re-?schedule|"
    r"different\s+(?:time|day)|"
    r"later\s+(?:today|this\s+week)|"
    r"pick\s+another\s+time|"
    r"book\s+another|"
    r"وقت\s+(?:مش|غير)\s+مناسب|"
    r"مش\s+فاضي|"
    r"غير\s+متاح|"
    r"أعد\s+الجدولة|"
    r"إعادة\s+جدولة|"
    r"موعد\s+آخر|"
    r"وقت\s+ثاني|"
    r"ما\s+أقدر\s+أكمل|"
    r"مقدرش\s+أكمل|"
    r"لازم\s+أأجل"
    r")",
    re.I,
)

_QA_PROGRESS_RE = re.compile(
    r"(?:"
    r"first\s+question|"
    r"next\s+question|"
    r"question\s+(?:one|two|three|\d+)|"
    r"tell\s+me\s+about|"
    r"can\s+you\s+describe|"
    r"describe\s+(?:a\s+)?challenge|"
    r"what\s+(?:is|was)\s+your\s+experience|"
    r"السؤال\s+(?:الأول|التالي|الثاني|الثالث|\d+)|"
    r"سؤال\s+(?:أول|تالي|واحد|اتنين|\d+)|"
    r"خبرت|خبرتك|خبرتك\s+إيه|"
    r"صف\s+لي|"
    r"احكي\s+(?:لي\s+)?عن|"
    r"ممكن\s+تحكي|"
    r"وريني\s+مثال"
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


def transcript_shows_interview_progress(
    transcript: str | None,
    *,
    session_signals: dict[str, Any] | None = None,
) -> bool:
    signals = session_signals if isinstance(session_signals, dict) else {}
    try:
        asked = int(signals.get("questions_asked") or 0)
    except (TypeError, ValueError):
        asked = 0
    if asked >= 1:
        return True

    text = str(transcript or "").strip()
    if not text:
        return False
    # Q&A markers count even on short transcripts (mid-interview stop → completed).
    if _QA_PROGRESS_RE.search(text):
        return True
    # Rough turn count needs enough text to avoid false positives on short intros.
    if len(text) < 220:
        return False
    lines = [ln for ln in re.split(r"[\n.]+", text) if len(ln.strip()) > 20]
    return len(lines) >= 8


def classify_interview_session_outcome_with_llm(
    db: Session,
    *,
    transcript: str,
    duration_seconds: int | None = None,
) -> InterviewSessionOutcome | None:
    """LLM Layer 2b: decide completed vs reschedule vs recording_declined vs wrong_person.

    Returns None on failure so callers can keep keyword classification.
    """
    text = str(transcript or "").strip()
    if len(text) < 40:
        return None
    try:
        from app.services.agents.base import AgentMessage
        from app.services.providers.openai_service import OpenAIProviderService

        prompt = (
            "You classify the END STATE of a job screening interview call/meeting.\n"
            "Return ONLY one lowercase label from this set:\n"
            "completed — candidate answered interview screening questions (even partially).\n"
            "reschedule — candidate said not free / busy / stop / reschedule BEFORE real Q&A answers.\n"
            "recording_declined — candidate refused recording consent.\n"
            "wrong_person — wrong person or wrong number.\n"
            "technical_abort — dropped/connection fail with almost no conversation.\n"
            f"Duration seconds (may be null): {duration_seconds}\n"
            "Transcript:\n"
            f"{text[:6000]}\n"
        )
        result = OpenAIProviderService.complete(
            db,
            system_prompt="Classify interview session outcomes. Reply with one label only.",
            messages=[AgentMessage(role="user", content=prompt)],
            max_tokens=20,
            temperature=0,
            provider="deepseek",
        )
        label = str(result.assistant_text or "").strip().lower().split()[0].strip(".,;:")
        allowed = {"completed", "reschedule", "recording_declined", "wrong_person", "technical_abort"}
        if label in allowed:
            return label  # type: ignore[return-value]
    except Exception:
        logger.exception("interview_session_llm_classify_failed")
    return None


def resolve_interview_session_outcome(
    db: Session | None,
    *,
    duration_seconds: int | None,
    transcript: str | None = None,
    use_llm: bool = False,
    session_signals: dict[str, Any] | None = None,
) -> InterviewSessionOutcome:
    """Keyword classify, optionally confirm/override with LLM when transcript is present."""
    keyword = classify_interview_session_outcome(
        duration_seconds=duration_seconds,
        transcript=transcript,
        session_signals=session_signals,
    )
    text = str(transcript or "").strip()
    if not use_llm or db is None or len(text) < 80:
        return keyword
    # Always ask LLM when keyword may conflict with mid-interview progress / reschedule wording.
    ambiguous = keyword in {"completed", "reschedule", "technical_abort"}
    if not ambiguous and keyword not in {"wrong_person"}:
        return keyword
    llm = classify_interview_session_outcome_with_llm(
        db, transcript=text, duration_seconds=duration_seconds
    )
    if llm is None:
        return keyword
    # Prefer LLM when keywords said completed but LLM says early exit (or vice versa for recording).
    if keyword == "completed" and llm in {"reschedule", "recording_declined", "wrong_person", "technical_abort"}:
        # Keep product rule A: real Q&A progress stays completed even if LLM says reschedule.
        if transcript_shows_interview_progress(text, session_signals=session_signals) and llm == "reschedule":
            return "completed"
        return llm
    if llm == "recording_declined":
        return llm
    if keyword in {"reschedule", "recording_declined", "wrong_person"} and llm == "completed":
        # Mid-interview stop stays completed (product rule A) if LLM saw real Q&A.
        return "completed"
    return llm if llm != keyword else keyword


def classify_interview_session_outcome(
    *,
    duration_seconds: int | None,
    transcript: str | None = None,
    session_signals: dict[str, Any] | None = None,
) -> InterviewSessionOutcome:
    """Decide whether a connected session was a finished interview or an early exit.

    When a usable transcript is present, interview progress (not bare duration) gates
    whether a reschedule request mid-intro still unlocks booking.
    """
    secs = int(duration_seconds) if duration_seconds is not None else None
    text = str(transcript or "").strip()
    has_transcript = len(text) >= 40
    signals = session_signals if isinstance(session_signals, dict) else {}

    if signals.get("recording_consent") is False:
        return "recording_declined"

    if text and _RECORDING_DECLINE_RE.search(text):
        # Product choice B: recording decline is a hard stop (no rebook).
        return "recording_declined"

    progress = transcript_shows_interview_progress(text, session_signals=signals)
    if text and _WRONG_PERSON_RE.search(text) and not progress:
        return "wrong_person"

    # Layer 2 / transcript-aware: duration alone must not force "completed".
    if has_transcript or signals:
        substantial = progress
    else:
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


def _strip_completed_interview_artifacts(merged: dict[str, Any]) -> None:
    for key in (
        "ended_at",
        "call_completed_at",
        "meeting_ended_at",
        "analysis",
        "analysis_saved_at",
        "analysis_version",
        "analysis_error",
        "analysis_attempted_at",
        "score",
        "recommendation",
        "sentiment",
        "short_summary",
        "thank_you_email_sent_at",
        "thank_you_email_ok",
        "thank_you_email_attempted_at",
        "session_outcome_provisional",
    ):
        merged.pop(key, None)


def _maybe_reopen_order_after_early_exit(db: Session, order: ServiceOrder) -> None:
    """If the campaign was closed only because this contact looked done, reopen it."""
    if str(order.status or "").lower() != "completed":
        return
    recipients = list(
        db.execute(
            select(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id)
        ).scalars()
    )
    still_open = any(
        str(r.status or "").lower() not in {"completed", "done", "opted_out", "cancelled", "skipped", "failed", "no_answer", "busy"}
        for r in recipients
    )
    if not still_open:
        return
    order.status = "running"
    order.completed_at = None
    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()
    db.refresh(order)


def maybe_reclassify_completed_interview_after_transcript(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
) -> dict[str, Any] | None:
    """Layer 2: after STT arrives, correct a provisional/wrong 'completed' outcome.

    Returns the apply result when the outcome changes away from completed; otherwise None.
    """
    db.refresh(recipient)
    status = str(recipient.status or "").lower()
    if status not in {"completed", "done"}:
        return None

    merged = _recipient_result(recipient)
    if merged.get("session_outcome_reviewed_at"):
        return None

    transcript = str(merged.get("transcript") or "").strip()
    if len(transcript) < 40:
        return None

    secs = merged.get("duration_seconds")
    try:
        duration = int(secs) if secs is not None else None
    except (TypeError, ValueError):
        duration = None

    outcome = resolve_interview_session_outcome(
        db,
        duration_seconds=duration,
        transcript=transcript,
        use_llm=True,
        session_signals=merged.get("session_signals") if isinstance(merged.get("session_signals"), dict) else {},
    )
    reviewed_at = datetime.utcnow().isoformat()

    if outcome == "completed":
        _set_recipient_result(
            db,
            recipient,
            {
                "session_outcome": "completed",
                "session_outcome_reviewed_at": reviewed_at,
                "session_outcome_provisional": False,
                "awaiting_candidate_action": False,
                "session_outcome_layer": "transcript_review_llm",
            },
        )
        return None

    channel = str(merged.get("channel") or merged.get("call_channel") or "meeting").strip() or "meeting"
    # Clear completed artifacts before applying the corrected early-exit outcome.
    cleaned = _recipient_result(recipient)
    _strip_completed_interview_artifacts(cleaned)
    cleaned["session_outcome_reviewed_at"] = reviewed_at
    cleaned["session_outcome_layer"] = "transcript_review"
    recipient.result_json = json.dumps(cleaned, ensure_ascii=False)
    recipient.status = "pending"
    recipient.updated_at = datetime.utcnow()
    db.add(recipient)
    db.commit()
    db.refresh(recipient)

    result = apply_interview_session_outcome(
        db,
        order=order,
        recipient=recipient,
        outcome=outcome,
        duration_seconds=duration,
        transcript=transcript,
        channel="meeting" if channel == "meeting" else "ai_call",
        extra={
            "session_outcome_reviewed_at": reviewed_at,
            "session_outcome_layer": "transcript_review",
            "corrected_from_status": "completed",
        },
    )
    try:
        _maybe_reopen_order_after_early_exit(db, order)
    except Exception:
        logger.exception(
            "interview_reopen_order_after_early_exit_failed order=%s recipient=%s",
            order.id,
            recipient.id,
        )
    try:
        from app.services.interview_analysis_service import refresh_order_interview_report

        refresh_order_interview_report(db, order)
    except Exception:
        logger.exception("interview_report_refresh_after_reclassify_failed")
    logger.info(
        "interview_session_reclassified",
        extra={
            "order_id": order.id,
            "recipient_id": recipient.id,
            "outcome": outcome,
        },
    )
    return result


def interview_ready_for_completion_side_effects(
    *,
    recipient: ServiceOrderRecipient,
    transcript: str | None = None,
) -> bool:
    """True when transcript review confirms a real completed interview (Layer 2)."""
    merged = _recipient_result(recipient)
    stored = str(merged.get("session_outcome") or "").lower()
    if stored and stored != "completed":
        return False
    text = str(transcript if transcript is not None else merged.get("transcript") or "").strip()
    if merged.get("session_outcome_reviewed_at"):
        return stored in {"", "completed"}
    if len(text) < 40:
        return False
    secs = merged.get("duration_seconds")
    try:
        duration = int(secs) if secs is not None else None
    except (TypeError, ValueError):
        duration = None
    return classify_interview_session_outcome(duration_seconds=duration, transcript=text) == "completed"


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
    """Persist outcome. Emails are outcome-gated; usage metering is per connected call."""
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

    def _meter_connected_call() -> None:
        """Charge per connected call/meeting minutes — any outcome (not only completed)."""
        try:
            from app.services.billing_call_minutes import billable_call_minutes
            from app.services.interview_session_billing_service import meter_session_if_needed

            if duration_seconds is not None and not patch.get("billable_minutes"):
                patch["billable_minutes"] = billable_call_minutes(int(duration_seconds))
            # Persist duration/billable before metering so wallet sees minutes.
            merged = _recipient_result(recipient)
            if duration_seconds is not None:
                merged["duration_seconds"] = int(duration_seconds)
            if patch.get("billable_minutes") is not None:
                merged["billable_minutes"] = patch["billable_minutes"]
            recipient.result_json = json.dumps(merged, ensure_ascii=False)
            db.add(recipient)
            db.commit()
            db.refresh(recipient)
            meter_session_if_needed(db, order, recipient)
        except Exception:
            logger.exception("interview_session_meter_on_outcome_failed")

    if outcome == "completed":
        patch.pop("early_exit_at", None)
        patch["awaiting_candidate_action"] = False
        patch["ended_at"] = now_iso
        patch["call_completed_at"] = now_iso
        # Provisional until Layer 2 reviews the transcript (unless already reviewed).
        if not patch.get("session_outcome_reviewed_at") and len(str(transcript or "").strip()) < 40:
            patch["session_outcome_provisional"] = True
        else:
            patch["session_outcome_provisional"] = False
        if channel == "meeting":
            patch["meeting_ended_at"] = now_iso
        recipient.status = "completed"
        recipient.updated_at = now
        _set_recipient_result(db, recipient, {k: v for k, v in patch.items() if v is not None})
        _meter_connected_call()
        # Phone has no web end-screen — thank-you is email only (no interview thank-you WA template).
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
        _meter_connected_call()
        try:
            from app.services.interview_session_outcome_email_service import (
                dispatch_interview_session_outcome_email,
            )

            dispatch_interview_session_outcome_email(
                db, order=order, recipient=recipient, outcome="recording_declined"
            )
        except Exception:
            logger.exception("interview_opt_out_email_failed")
        try:
            from app.services.interview_outcome_whatsapp_service import maybe_send_interview_outcome_whatsapp

            maybe_send_interview_outcome_whatsapp(
                db, order=order, recipient=recipient, outcome="recording_declined", channel=channel
            )
        except Exception:
            logger.exception("interview_opt_out_wa_failed")
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
    _strip_completed_interview_artifacts(merged)
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    db.add(recipient)
    db.commit()
    db.refresh(recipient)
    _meter_connected_call()

    email_sent = False
    if outcome == "reschedule":
        try:
            from app.services.interview_session_outcome_email_service import (
                dispatch_interview_session_outcome_email,
            )

            mail = dispatch_interview_session_outcome_email(
                db, order=order, recipient=recipient, outcome="reschedule"
            )
            email_sent = bool(mail.get("ok") or mail.get("skipped") and mail.get("reason") == "already_sent")
        except Exception:
            logger.exception("interview_session_reschedule_email_failed")
            email_sent = _send_reschedule_email(db, order, recipient)

    try:
        from app.services.interview_outcome_whatsapp_service import maybe_send_interview_outcome_whatsapp

        maybe_send_interview_outcome_whatsapp(
            db, order=order, recipient=recipient, outcome=outcome, channel=channel
        )
    except Exception:
        logger.exception("interview_outcome_wa_failed")

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
