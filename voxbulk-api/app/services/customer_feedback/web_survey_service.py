"""Web survey sessions for Customer Feedback QR flows."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.customer_feedback import (
    FeedbackIndustry,
    FeedbackLocation,
    FeedbackResponse,
    FeedbackSession,
    FeedbackSurveyType,
)
from app.models.organisation import Organisation
from app.services.customer_feedback.billing_service import FeedbackBillingService
from app.services.customer_feedback.feedback_marketing_policy import is_marketing_survey_step
from app.services.customer_feedback.location_service import FeedbackLocationService, location_to_dict
from app.services.customer_feedback.survey_config_service import (
    format_template_message,
    load_survey_config,
    repair_survey_config_if_needed,
    template_for_step,
)
from app.services.customer_feedback.whatsapp_service import FeedbackWhatsappService


def _web_steps(db: Session, location: FeedbackLocation) -> list[dict[str, Any]]:
    steps = FeedbackWhatsappService._steps_for_location(db, location)
    return [step for step in steps if not is_marketing_survey_step(step)]


# Rating choices for topic questions (web survey). "Poor" is the low value that triggers
# the "why did you rate poor?" follow-up screen on the web client.
_RATING_OPTIONS = [
    {"label": "😊 Excellent", "value": "Excellent"},
    {"label": "🙂 Good", "value": "Good"},
    {"label": "😞 Poor", "value": "Poor"},
]
_LOW_RATING_VALUES = ["Poor"]

# Suggested reasons shown on the low-rating follow-up screen (English-only web survey).
_LOW_RATING_REASONS = ["Service", "Speed", "Staff", "Price", "Cleanliness", "Quality"]


def _step_to_question(db: Session, location: FeedbackLocation, step: dict[str, Any], *, language: str | None) -> dict[str, Any]:
    kind = str(step.get("kind") or "topic")
    tpl = template_for_step(db, location, step, language=language)
    survey_type_id = str(step.get("survey_type_id") or location.survey_type_id or "")
    survey_type = db.get(FeedbackSurveyType, survey_type_id) if survey_type_id else None
    title = survey_type.name if survey_type else (tpl.template_key if tpl else kind)
    body = format_template_message(tpl) if tpl else title
    if kind == "open_question":
        return {
            "kind": kind,
            "title": title,
            "body": body,
            "input": "text",
            "options": [],
            "allow_voice": True,
            "is_rating": False,
        }
    if kind == "tell_us_more":
        return {
            "kind": kind,
            "title": "Tell us more",
            "body": body or "What could we do better?",
            "input": "text",
            "options": [{"label": "Skip", "value": "skip"}],
            "allow_voice": True,
            "is_rating": False,
        }
    return {
        "kind": kind,
        "title": title,
        "body": body,
        "input": "choice",
        "options": list(_RATING_OPTIONS),
        "allow_voice": False,
        "is_rating": True,
        "low_values": list(_LOW_RATING_VALUES),
        "reason_options": list(_LOW_RATING_REASONS),
        "reason_prompt": "Sorry to hear that. What went wrong?",
    }


class FeedbackWebSurveyService:
    @staticmethod
    def survey_payload(db: Session, token: str) -> dict[str, Any]:
        location = FeedbackLocationService.resolve_by_token(db, token)
        if location is None:
            raise ValueError("Survey not found")
        org = db.get(Organisation, location.org_id)
        industry = db.get(FeedbackIndustry, location.industry_id)
        base = get_settings().public_site_base_url.rstrip("/")
        loc = location_to_dict(db, location)
        steps = _web_steps(db, location)
        lang = "en_GB"
        questions = [_step_to_question(db, location, step, language=lang) for step in steps]
        return {
            "token": token,
            "company_name": org.name if org else "Your business",
            "branch_name": location.name or location.branch_code,
            "industry_name": industry.name if industry else None,
            "wa_url": loc.get("wa_url"),
            "web_survey_url": f"{base}/survey/{token}",
            "open_question_enabled": bool(location.open_question_enabled),
            "step_count": len(questions),
            "questions": questions,
        }

    @staticmethod
    def start_session(db: Session, token: str) -> dict[str, Any]:
        location = FeedbackLocationService.resolve_by_token(db, token)
        if location is None:
            raise ValueError("Survey not found")
        ok, reason = FeedbackBillingService.ensure_web_units_available(db, location.org_id)
        if not ok:
            raise ValueError(reason or "Customer feedback is unavailable right now.")
        steps = _web_steps(db, location)
        if not steps:
            raise ValueError("Survey has no questions configured")

        visitor_id = str(uuid.uuid4())
        visitor_phone = f"web:{visitor_id}"
        dedupe_key = f"{visitor_phone}:{token}"
        FeedbackLocationService.record_scan(db, location)
        repair_survey_config_if_needed(db, location)
        now = datetime.utcnow()
        session = FeedbackSession(
            id=str(uuid.uuid4()),
            org_id=location.org_id,
            location_id=location.id,
            visitor_phone=visitor_phone,
            status="active",
            current_step=0,
            detected_language="en_GB",
            trigger_dedupe_key=dedupe_key,
            started_at=now,
            created_at=now,
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        FeedbackBillingService.consume_web_unit(db, location.org_id)
        session.units_charged = True
        db.add(session)
        db.commit()

        question = _step_to_question(db, location, steps[0], language=session.detected_language)
        return {
            "session_id": session.id,
            "step_index": 0,
            "step_count": len(steps),
            "question": question,
        }

    @staticmethod
    def get_active_web_session(db: Session, session_id: str) -> FeedbackSession:
        session = db.get(FeedbackSession, session_id)
        if session is None or session.status != "active":
            raise ValueError("Session not found or expired")
        if not str(session.visitor_phone or "").startswith("web:"):
            raise ValueError("Not a web survey session")
        return session

    @staticmethod
    def _save_low_rating_reason(
        db: Session,
        *,
        session: FeedbackSession,
        location: FeedbackLocation,
        step: dict[str, Any],
        step_index: int,
        reason: str,
        reason_source: str = "text",
    ) -> None:
        """Record the 'why did you rate poor?' answer as its own response row."""
        reason = str(reason or "").strip()
        if not reason or reason.lower() == "skip":
            return
        tpl = template_for_step(db, location, step, language=session.detected_language)
        survey_type_id = str(step.get("survey_type_id") or location.survey_type_id)
        db.add(
            FeedbackResponse(
                id=str(uuid.uuid4()),
                session_id=session.id,
                org_id=session.org_id,
                location_id=session.location_id,
                survey_type_id=survey_type_id,
                question_key=f"{(tpl.template_key if tpl else str(step.get('template_key') or step.get('kind')))}__low_reason",
                answer_text=reason,
                original_text=reason,
                answer_text_en=reason,
                step_order=step_index + 1,
                answer_source=(reason_source or "text")[:16],
                created_at=datetime.utcnow(),
            )
        )

    @staticmethod
    def submit_answer(
        db: Session,
        *,
        session_id: str,
        answer: str,
        answer_source: str = "text",
        reason: str | None = None,
        reason_source: str = "text",
    ) -> dict[str, Any]:
        session = FeedbackWebSurveyService.get_active_web_session(db, session_id)

        location = db.get(FeedbackLocation, session.location_id)
        if location is None:
            raise ValueError("Location not found")

        steps = _web_steps(db, location)
        step_index = int(session.current_step or 0)
        if step_index >= len(steps):
            return {"completed": True, "thank_you": True}

        current_step = steps[step_index]
        tpl = template_for_step(db, location, current_step, language=session.detected_language)

        if str(answer).strip().lower() != "skip":
            FeedbackWhatsappService._save_answer(
                db,
                session=session,
                location=location,
                step=current_step,
                tpl=tpl,
                answer=answer,
                step_index=step_index,
                answer_source=answer_source,
            )

        # Capture an optional low-rating reason ("why did you rate poor?") alongside the rating.
        if reason:
            FeedbackWebSurveyService._save_low_rating_reason(
                db,
                session=session,
                location=location,
                step=current_step,
                step_index=step_index,
                reason=reason,
                reason_source=reason_source,
            )

        next_index = step_index + 1
        session.current_step = next_index

        if next_index >= len(steps):
            session.status = "completed"
            session.completed_at = datetime.utcnow()
            db.add(session)
            db.commit()
            return {"completed": True, "thank_you": True}

        db.add(session)
        db.commit()
        question = _step_to_question(db, location, steps[next_index], language=session.detected_language)
        return {
            "completed": False,
            "step_index": next_index,
            "step_count": len(steps),
            "question": question,
        }

    @staticmethod
    def submit_voice(
        db: Session,
        *,
        session_id: str,
        audio_bytes: bytes,
        filename: str,
        content_type: str,
        mode: str = "answer",
    ) -> dict[str, Any]:
        """Transcode + transcribe an uploaded voice note for the current web step.

        mode="answer": records the transcript as the current step answer and advances.
        mode="reason": records a low-rating reason for the current step (no advance).
        Returns the transcript plus, for mode="answer", the next question / completion.
        """
        from app.services.voice_transcription_service import VoiceTranscriptionService

        session = FeedbackWebSurveyService.get_active_web_session(db, session_id)
        location = db.get(FeedbackLocation, session.location_id)
        if location is None:
            raise ValueError("Location not found")
        if not audio_bytes:
            raise ValueError("Empty audio upload")

        result = VoiceTranscriptionService.transcribe_uploaded_audio(
            db,
            audio_bytes=audio_bytes,
            filename=filename or "voice.webm",
            content_type=content_type or "audio/webm",
            language="en",
        )
        transcript = str(getattr(result, "transcript", "") or "").strip()
        if not transcript or not getattr(result, "ok", False):
            err = str(getattr(result, "error", "") or "").strip()
            raise ValueError(
                err or "Could not transcribe your voice note. Please type your answer instead."
            )

        if mode == "reason":
            steps = _web_steps(db, location)
            step_index = int(session.current_step or 0)
            if step_index < len(steps) and transcript:
                FeedbackWebSurveyService._save_low_rating_reason(
                    db,
                    session=session,
                    location=location,
                    step=steps[step_index],
                    step_index=step_index,
                    reason=transcript,
                    reason_source="voice",
                )
                db.commit()
            return {"transcript": transcript, "saved": bool(transcript)}

        # mode == "answer": treat transcript as the step's text answer (advances the flow).
        return {
            "transcript": transcript,
            **FeedbackWebSurveyService.submit_answer(
                db,
                session_id=session_id,
                answer=transcript,
                answer_source="voice",
            ),
        }
