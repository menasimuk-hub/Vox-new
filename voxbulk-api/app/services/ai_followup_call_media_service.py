"""Transcript, recording, and customer reason for AI follow-up voice calls."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.call_log import CallLog
from app.models.customer_feedback import FeedbackAiFollowUpJob
from app.models.survey_ai_follow_up_job import SurveyAiFollowUpJob
from app.services.ai_followup_report_service import extract_customer_lines_from_transcript
from app.utils.transcript_sanitize import sanitize_transcript_document, sanitize_transcript_markup
from app.services.customer_feedback.feedback_ai_followup_service import _job_outcome, _set_job_outcome
from app.services.survey_analysis_service import MIN_TRANSCRIPT_CHARS, fetch_survey_transcript_from_telnyx

logger = logging.getLogger(__name__)

USER_RECORDING_UNAVAILABLE = "Recording is temporarily unavailable. Please try again in a minute."
USER_RECORDING_PROCESSING = "Recording is still processing. Please try again shortly."


def _format_transcript_lines(transcript: str) -> list[dict[str, str]]:
    lines: list[dict[str, str]] = []
    for raw in str(transcript or "").splitlines():
        clean = raw.strip()
        if not clean:
            continue
        speaker = "Agent"
        text = clean
        if ":" in clean:
            head, rest = clean.split(":", 1)
            head_low = head.strip().lower()
            if head_low in {"agent", "candidate", "user", "assistant", "customer", "caller"}:
                speaker = head.strip().title()
                if speaker.lower() in {"user", "customer", "caller"}:
                    speaker = "Customer"
                elif speaker.lower() == "assistant":
                    speaker = "Agent"
                text = sanitize_transcript_markup(rest.strip())
        else:
            text = sanitize_transcript_markup(text)
        if not text:
            continue
        lines.append({"speaker": speaker, "text": text})
    return lines


def _recording_play_path(job_id: str) -> str:
    return f"/service-orders/ai-follow-up-jobs/{job_id}/recording"


def _loads_outcome(job: SurveyAiFollowUpJob | FeedbackAiFollowUpJob) -> dict[str, Any]:
    return _job_outcome(job)


def _persist_outcome(db: Session, job: SurveyAiFollowUpJob | FeedbackAiFollowUpJob, patch: dict[str, Any]) -> dict[str, Any]:
    _set_job_outcome(job, patch)
    job.updated_at = datetime.utcnow()
    db.add(job)
    db.commit()
    db.refresh(job)
    return _job_outcome(job)


def resolve_ai_followup_job(
    db: Session,
    *,
    job_id: str,
    org_id: str,
) -> SurveyAiFollowUpJob | FeedbackAiFollowUpJob:
    wa = db.get(SurveyAiFollowUpJob, job_id)
    if wa is not None and str(wa.org_id) == str(org_id):
        return wa
    cf = db.get(FeedbackAiFollowUpJob, job_id)
    if cf is not None and str(cf.org_id) == str(org_id):
        return cf
    raise LookupError("AI follow-up job not found")


def _call_control_id(job: SurveyAiFollowUpJob | FeedbackAiFollowUpJob, outcome: dict[str, Any]) -> str:
    return str(job.call_id or outcome.get("call_control_id") or "").strip()


def _duration_label(seconds: int | None) -> str | None:
    if seconds is None or seconds < 0:
        return None
    if seconds < 60:
        return f"{seconds}s"
    m = seconds // 60
    s = seconds % 60
    return f"{m}m {s:02d}s"


def _extract_call_reason(*, transcript: str, call_summary: str | None) -> str | None:
    summary = str(call_summary or "").strip()
    if summary:
        return summary
    customer = extract_customer_lines_from_transcript(transcript)
    if customer and len(customer) >= 12:
        return customer
    lines = _format_transcript_lines(transcript)
    customer_text = " ".join(
        ln["text"] for ln in lines if str(ln.get("speaker") or "").lower() == "customer" and ln.get("text")
    ).strip()
    if customer_text:
        return customer_text[:1200]
    return None


def ensure_ai_followup_call_media(db: Session, job: SurveyAiFollowUpJob | FeedbackAiFollowUpJob) -> dict[str, Any]:
    """Hydrate transcript + recording metadata from CallLog and Telnyx (idempotent)."""
    outcome = _loads_outcome(job)
    call_id = _call_control_id(job, outcome)
    transcript = str(outcome.get("transcript") or outcome.get("transcript_excerpt") or "").strip()

    log = None
    if call_id:
        log = db.execute(select(CallLog).where(CallLog.external_call_id == call_id)).scalar_one_or_none()
        if log and log.transcript_text:
            log_text = str(log.transcript_text).strip()
            if len(log_text) > len(transcript):
                transcript = log_text
        if log and log.recording_url and not outcome.get("recording_url"):
            outcome["recording_url"] = log.recording_url

    patch: dict[str, Any] = {}
    if call_id and not outcome.get("call_control_id"):
        patch["call_control_id"] = call_id
    if log and log.id and not outcome.get("call_log_id"):
        patch["call_log_id"] = log.id

    if len(transcript) < MIN_TRANSCRIPT_CHARS and call_id:
        try:
            telnyx_data = fetch_survey_transcript_from_telnyx(
                db,
                call_control_id=call_id,
                started_at=getattr(job, "created_at", None) or datetime.utcnow(),
            )
            for key, val in telnyx_data.items():
                if key == "transcript_fetch_error" or val in (None, ""):
                    continue
                patch[key] = val
            fetched = str(telnyx_data.get("transcript") or "").strip()
            if len(fetched) > len(transcript):
                transcript = fetched
        except Exception:
            logger.exception("ai_followup_telnyx_hydrate_failed job_id=%s", job.id)

    if transcript:
        transcript = sanitize_transcript_document(transcript)
        patch["transcript"] = transcript
        patch["transcript_excerpt"] = transcript[:800]
        if not outcome.get("transcript_saved_at"):
            patch["transcript_saved_at"] = datetime.utcnow().isoformat()

    call_summary = str(patch.get("call_summary") or outcome.get("call_summary") or "").strip()
    call_reason = _extract_call_reason(transcript=transcript, call_summary=call_summary or None)
    if call_reason:
        patch["call_reason"] = call_reason

    has_recording = bool(
        patch.get("telnyx_recording_download_url")
        or outcome.get("telnyx_recording_download_url")
        or patch.get("recording_url")
        or outcome.get("recording_url")
        or patch.get("telnyx_conversation_id")
        or outcome.get("telnyx_conversation_id")
        or call_id
    )
    patch["has_recording"] = has_recording

    if patch:
        outcome = _persist_outcome(db, job, patch)
    elif transcript:
        outcome["transcript"] = sanitize_transcript_document(transcript)

    return outcome


def build_ai_followup_call_detail(db: Session, job: SurveyAiFollowUpJob | FeedbackAiFollowUpJob) -> dict[str, Any]:
    outcome = ensure_ai_followup_call_media(db, job)
    transcript = sanitize_transcript_document(
        str(outcome.get("transcript") or outcome.get("transcript_excerpt") or "").strip()
    )
    call_reason = str(outcome.get("call_reason") or "").strip() or _extract_call_reason(
        transcript=transcript,
        call_summary=str(outcome.get("call_summary") or "").strip() or None,
    )
    duration_seconds = outcome.get("duration_seconds")
    if not isinstance(duration_seconds, int):
        try:
            duration_seconds = int(duration_seconds) if duration_seconds is not None else None
        except (TypeError, ValueError):
            duration_seconds = None

    has_recording = bool(outcome.get("has_recording"))
    status = str(job.status or "").strip().lower()

    if not call_reason and status in {"completed", "opted_out"}:
        if transcript:
            call_reason = extract_customer_lines_from_transcript(transcript) or None
        if not call_reason:
            call_reason = (
                "The AI call finished but the customer's explanation is still syncing. "
                "Open the transcript or refresh in a minute."
            )

    return {
        "ok": True,
        "job_id": job.id,
        "status": job.status,
        "call_reason": call_reason,
        "transcript": transcript,
        "transcript_lines": _format_transcript_lines(transcript),
        "has_recording": has_recording,
        "recording_play_url": _recording_play_path(job.id) if has_recording else None,
        "duration_seconds": duration_seconds,
        "duration_label": _duration_label(duration_seconds),
        "hangup_cause": outcome.get("hangup_cause"),
        "call_id": job.call_id,
    }


def _media_type_for_format(fmt: str) -> str:
    return "audio/wav" if str(fmt or "").lower() == "wav" else "audio/mpeg"


def fetch_ai_followup_recording(
    db: Session,
    job: SurveyAiFollowUpJob | FeedbackAiFollowUpJob,
) -> tuple[bytes, str] | None:
    outcome = ensure_ai_followup_call_media(db, job)
    conversation_id = str(outcome.get("telnyx_conversation_id") or "").strip()

    if conversation_id:
        from app.services.telnyx_conversation_service import (
            fetch_conversation_by_id,
            resolve_telnyx_recording_relaxed,
        )

        conversation = fetch_conversation_by_id(db, conversation_id)
        if conversation:
            rec = resolve_telnyx_recording_relaxed(db, conversation)
            if rec:
                audio = rec.get("audio_bytes")
                if isinstance(audio, (bytes, bytearray)) and audio:
                    _persist_outcome(
                        db,
                        job,
                        {
                            "telnyx_recording_download_url": rec.get("download_url"),
                            "telnyx_recording_id": rec.get("id"),
                        },
                    )
                    return bytes(audio), _media_type_for_format(str(rec.get("format") or "mp3"))
                url = str(rec.get("download_url") or "").strip()
                if url.startswith("http"):
                    try:
                        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                            resp = client.get(url)
                            resp.raise_for_status()
                        media_type = resp.headers.get("content-type") or "audio/mpeg"
                        return resp.content, media_type
                    except Exception:
                        logger.exception("ai_followup_recording_download_failed job_id=%s", job.id)

    for key in ("telnyx_recording_download_url", "recording_url"):
        url = str(outcome.get(key) or "").strip()
        if url.startswith("http"):
            try:
                with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                    resp = client.get(url)
                    resp.raise_for_status()
                media_type = resp.headers.get("content-type") or "audio/mpeg"
                return resp.content, media_type
            except Exception:
                logger.exception("ai_followup_recording_url_failed job_id=%s key=%s", job.id, key)

    call_id = _call_control_id(job, outcome)
    if call_id:
        log = db.execute(select(CallLog).where(CallLog.external_call_id == call_id)).scalar_one_or_none()
        if log and log.recording_url and str(log.recording_url).startswith("http"):
            try:
                with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                    resp = client.get(str(log.recording_url))
                    resp.raise_for_status()
                media_type = resp.headers.get("content-type") or "audio/mpeg"
                return resp.content, media_type
            except Exception:
                logger.exception("ai_followup_call_log_recording_failed job_id=%s", job.id)

    return None


def attach_call_media_to_report(db: Session, report: dict[str, Any], job: SurveyAiFollowUpJob | FeedbackAiFollowUpJob) -> dict[str, Any]:
    """Lightweight enrich for list/results payloads (uses stored outcome; hydrates if completed and empty)."""
    status = str(job.status or "").strip().lower()
    outcome = _loads_outcome(job)
    if status in {"completed", "opted_out", "voicemail", "busy", "no_answer"} and not outcome.get("transcript"):
        try:
            outcome = ensure_ai_followup_call_media(db, job)
        except Exception:
            logger.exception("ai_followup_report_hydrate_failed job_id=%s", job.id)

    transcript = sanitize_transcript_document(
        str(outcome.get("transcript") or outcome.get("transcript_excerpt") or "").strip()
    )
    call_reason = str(outcome.get("call_reason") or "").strip() or _extract_call_reason(
        transcript=transcript,
        call_summary=str(outcome.get("call_summary") or "").strip() or None,
    )
    duration_seconds = outcome.get("duration_seconds")
    has_recording = bool(outcome.get("has_recording")) or bool(
        outcome.get("telnyx_conversation_id") or outcome.get("telnyx_recording_download_url") or job.call_id
    )

    report["call_reason"] = call_reason
    report["transcript_preview"] = transcript[:400] if transcript else None
    report["has_recording"] = has_recording
    report["recording_play_url"] = _recording_play_path(job.id) if has_recording else None
    report["duration_label"] = _duration_label(
        int(duration_seconds) if isinstance(duration_seconds, int) else None
    )
    return report
