"""Web survey sessions for Customer Feedback QR flows."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
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
from app.services.customer_feedback.locale_service import map_stt_language_code
from app.services.customer_feedback.feedback_marketing_policy import is_marketing_survey_step
from app.services.customer_feedback.location_service import FeedbackLocationService, location_to_dict
from app.services.customer_feedback.survey_config_service import (
    format_template_message,
    load_survey_config,
    repair_survey_config_if_needed,
    template_for_step,
)
from app.services.customer_feedback.feedback_answer_service import is_negative_topic_answer
from app.services.customer_feedback.feedback_wa_session_state import (
    clear_tell_us_more_pending,
    is_tell_us_more_pending,
    load_feedback_session_state,
    save_feedback_session_state,
    set_tell_us_more_pending,
    parse_deadline,
)
from app.services.customer_feedback.whatsapp_service import FeedbackWhatsappService
from app.services.customer_feedback.web_theme_service import (
    load_web_theme_from_location,
    parse_web_theme_config,
    resolve_theme_id,
)
from app.services.org_logo_storage_service import media_type_for_key, resolve_logo_path

logger = logging.getLogger(__name__)


def _maybe_schedule_ai_followup(db: Session, session: FeedbackSession, location: FeedbackLocation) -> None:
    try:
        from app.services.customer_feedback.feedback_ai_followup_service import schedule_if_eligible

        schedule_if_eligible(db, session=session, location=location)
    except Exception:
        logger.exception("feedback_ai_followup_schedule_failed session_id=%s", session.id)


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
        has_logo = bool(org and getattr(org, "logo_storage_key", None))
        web_theme = load_web_theme_from_location(location)
        industry_slug = industry.slug if industry else None
        theme_id = resolve_theme_id(industry_slug=industry_slug, web_theme=web_theme)
        config_raw = parse_web_theme_config(getattr(location, "survey_config_json", None))
        ai_follow_up = config_raw.get("ai_follow_up") if isinstance(config_raw.get("ai_follow_up"), dict) else None
        return {
            "token": token,
            "company_name": org.name if org else "Your business",
            "branch_name": location.name or location.branch_code,
            "industry_name": industry.name if industry else None,
            "industry_slug": industry_slug,
            "wa_url": loc.get("wa_url"),
            "logo_url": f"/public/feedback/survey/{token}/logo" if has_logo else None,
            "web_survey_url": f"{base}/survey/{token}",
            "open_question_enabled": bool(location.open_question_enabled),
            "step_count": len(questions),
            "questions": questions,
            "theme_id": theme_id,
            "web_theme": web_theme or None,
            "ai_follow_up": ai_follow_up,
        }

    @staticmethod
    def survey_logo(db: Session, token: str) -> tuple[Path, str]:
        """Resolve the org logo file for a survey token. Raises ValueError if missing."""
        location = FeedbackLocationService.resolve_by_token(db, token)
        if location is None:
            raise ValueError("Survey not found")
        org = db.get(Organisation, location.org_id)
        storage_key = getattr(org, "logo_storage_key", None) if org else None
        if not storage_key:
            raise ValueError("Logo not found")
        path = resolve_logo_path(str(storage_key))
        if path is None:
            raise ValueError("Logo not found")
        return path, media_type_for_key(str(storage_key))

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
    def _detect_language_from_text(
        text: str,
        session: FeedbackSession,
        *,
        stt_language: str | None = None,
    ) -> str:
        if stt_language:
            mapped = map_stt_language_code(stt_language)
            if mapped:
                return mapped

        from app.utils.script_language import detect_script_language

        lang = detect_script_language(str(text or ""))
        if lang == "ar":
            return "ar"
        if lang == "fr":
            return "fr_FR"
        return str(session.detected_language or "en_GB")

    @staticmethod
    def _apply_detected_language(
        db: Session,
        *,
        session: FeedbackSession,
        text: str,
        stt_language: str | None = None,
    ) -> str:
        detected = FeedbackWebSurveyService._detect_language_from_text(
            text,
            session,
            stt_language=stt_language,
        )
        if detected != session.detected_language:
            session.detected_language = detected
            db.add(session)
            db.flush()
        return detected

    @staticmethod
    def _voice_translation_fields(
        db: Session,
        *,
        text: str,
        session: FeedbackSession,
        tpl=None,
        source_language: str | None = None,
    ) -> dict[str, str]:
        from app.services.customer_feedback.feedback_answer_service import translate_answer_to_english

        detected = FeedbackWebSurveyService._detect_language_from_text(
            text,
            session,
            stt_language=source_language,
        )
        translated = translate_answer_to_english(
            db,
            answer=str(text or "").strip(),
            detected_language=detected,
            tpl=tpl,
            source_language=source_language,
        )
        original = str(translated.get("original_text") or text or "").strip()
        answer_en = str(translated.get("answer_text_en") or original).strip()
        return {
            "answer_text": answer_en,
            "original_text": original,
            "answer_text_en": answer_en,
            "translation_status": str(translated.get("translation_status") or ""),
        }

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
        fields = FeedbackWebSurveyService._voice_translation_fields(
            db, text=reason, session=session, tpl=tpl
        )
        db.add(
            FeedbackResponse(
                id=str(uuid.uuid4()),
                session_id=session.id,
                org_id=session.org_id,
                location_id=session.location_id,
                survey_type_id=survey_type_id,
                question_key=f"{(tpl.template_key if tpl else str(step.get('template_key') or step.get('kind')))}__low_reason",
                answer_text=fields["answer_text"],
                original_text=fields["original_text"],
                answer_text_en=fields["answer_text_en"],
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
        source_language: str | None = None,
    ) -> dict[str, Any]:
        session = FeedbackWebSurveyService.get_active_web_session(db, session_id)

        location = db.get(FeedbackLocation, session.location_id)
        if location is None:
            raise ValueError("Location not found")

        steps = _web_steps(db, location)
        state = load_feedback_session_state(session)

        if is_tell_us_more_pending(state):
            step_index = int(state.get("tell_us_more_step_index") or session.current_step or 0)
            reply = str(reason or answer or "").strip()
            if reply and reply.lower() != "skip":
                FeedbackWhatsappService._save_tell_us_more_answer(
                    db,
                    session=session,
                    location=location,
                    step_index=step_index,
                    topic_key=str(state.get("tell_us_more_topic_key") or "topic"),
                    survey_type_id=str(state.get("tell_us_more_survey_type_id") or location.survey_type_id),
                    answer=reply,
                    answer_source=reason_source if reason else answer_source,
                    source_language=source_language,
                )
            clear_tell_us_more_pending(state)
            save_feedback_session_state(session, state)
            session.current_step = step_index + 1
            db.add(session)
            db.commit()
            if session.current_step >= len(steps):
                session.status = "completed"
                session.completed_at = datetime.utcnow()
                db.add(session)
                db.commit()
                _maybe_schedule_ai_followup(db, session, location)
                return {"completed": True, "thank_you": True}
            question = _step_to_question(
                db, location, steps[session.current_step], language=session.detected_language
            )
            return {
                "completed": False,
                "step_index": session.current_step,
                "step_count": len(steps),
                "question": question,
            }

        step_index = int(session.current_step or 0)
        if step_index >= len(steps):
            return {"completed": True, "thank_you": True}

        current_step = steps[step_index]
        tpl = template_for_step(db, location, current_step, language=session.detected_language)

        if str(answer).strip().lower() != "skip":
            answer_text = str(answer or "").strip()
            if answer_text and answer_source == "text":
                FeedbackWebSurveyService._apply_detected_language(
                    db,
                    session=session,
                    text=answer_text,
                )
            FeedbackWhatsappService._save_answer(
                db,
                session=session,
                location=location,
                step=current_step,
                tpl=tpl,
                answer=answer,
                step_index=step_index,
                answer_source=answer_source,
                source_language=source_language,
            )

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
                _maybe_schedule_ai_followup(db, session, location)
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

        if (
            current_step.get("kind") == "topic"
            and tpl is not None
            and is_negative_topic_answer(
                db,
                answer=answer,
                tpl=tpl,
                detected_language=session.detected_language,
            )
        ):
            set_tell_us_more_pending(
                state,
                step_index=step_index,
                topic_key=str(tpl.template_key),
                survey_type_id=str(current_step.get("survey_type_id") or location.survey_type_id),
            )
            save_feedback_session_state(session, state)
            db.add(session)
            db.commit()
            tell_q = _step_to_question(
                db,
                location,
                {"kind": "tell_us_more", "template_key": "tell_us_more"},
                language=session.detected_language,
            )
            deadline = parse_deadline(state)
            return {
                "completed": False,
                "step_index": step_index,
                "step_count": len(steps),
                "question": tell_q,
                "pending_tell_us_more": True,
                "deadline_at": deadline.isoformat() if deadline else None,
            }

        next_index = step_index + 1
        session.current_step = next_index

        if next_index >= len(steps):
            session.status = "completed"
            session.completed_at = datetime.utcnow()
            db.add(session)
            db.commit()
            _maybe_schedule_ai_followup(db, session, location)
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
    def save_low_reason_for_previous_step(
        db: Session,
        *,
        session_id: str,
        reason: str,
        reason_source: str = "text",
    ) -> dict[str, Any]:
        """Attach a low-rating reason to the step immediately before current_step."""
        session = FeedbackWebSurveyService.get_active_web_session(db, session_id)
        location = db.get(FeedbackLocation, session.location_id)
        if location is None:
            raise ValueError("Location not found")

        steps = _web_steps(db, location)
        step_index = int(session.current_step or 0) - 1
        if step_index < 0:
            raise ValueError("No previous step to attach reason")
        if step_index >= len(steps):
            raise ValueError("Previous step not found")

        reason = str(reason or "").strip()
        if not reason or reason.lower() == "skip":
            return {"saved": False}

        FeedbackWebSurveyService._save_low_rating_reason(
            db,
            session=session,
            location=location,
            step=steps[step_index],
            step_index=step_index,
            reason=reason,
            reason_source=reason_source,
        )
        db.commit()
        return {"saved": True}

    @staticmethod
    def step_back(db: Session, session_id: str) -> dict[str, Any]:
        """Return to the previous step, discarding the answer saved for it."""
        session = FeedbackWebSurveyService.get_active_web_session(db, session_id)
        location = db.get(FeedbackLocation, session.location_id)
        if location is None:
            raise ValueError("Location not found")
        steps = _web_steps(db, location)
        step_index = int(session.current_step or 0)
        prev = max(0, step_index - 1)
        if step_index > 0:
            # Drop any response(s) recorded for the step we're returning to so a
            # re-answer does not create duplicates (answer + low-reason share step_order).
            rows = (
                db.execute(
                    select(FeedbackResponse).where(
                        FeedbackResponse.session_id == session.id,
                        FeedbackResponse.step_order == prev + 1,
                    )
                )
                .scalars()
                .all()
            )
            for row in rows:
                db.delete(row)
            session.current_step = prev
            db.add(session)
            db.commit()
        question = (
            _step_to_question(db, location, steps[prev], language=session.detected_language)
            if prev < len(steps)
            else None
        )
        return {
            "completed": False,
            "step_index": prev,
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
        answer: str | None = None,
    ) -> dict[str, Any]:
        """Transcode + transcribe an uploaded voice note for the current web step.

        answer set: submit `answer` as the step answer with the transcript as a voice
            reason, then advance (the low-rating reason screen "send voice note" case).
        mode="answer": records the transcript as the current step answer and advances.
        mode="reason": records a low-rating reason for the current step (no advance).
        Returns the transcript plus, for advancing modes, the next question / completion.
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
            language="auto",
        )
        transcript = str(getattr(result, "transcript", "") or "").strip()
        stt_error = str(getattr(result, "error", "") or "").strip()
        stt_language = getattr(result, "detected_language", None)
        transcode_ok = getattr(result, "transcode_ok", None)
        stt_provider = getattr(result, "stt_provider", None)

        if not transcript or not getattr(result, "ok", False):
            logger.warning(
                "voice_web_transcription_empty session=%s mode=%s stt_error=%s storage=%s "
                "transcode_ok=%s stt_provider=%s stt_language=%s",
                session_id,
                mode,
                stt_error or "empty_transcript",
                getattr(result, "storage_path", None),
                transcode_ok,
                stt_provider,
                stt_language,
            )
            return {
                "transcript": "",
                "saved": False,
                "stt_error": stt_error or "empty_transcript",
                "transcode_ok": transcode_ok,
                "stt_provider": stt_provider,
            }

        FeedbackWebSurveyService._apply_detected_language(
            db,
            session=session,
            text=transcript,
            stt_language=stt_language,
        )
        logger.info(
            "voice_web_transcription_ok session=%s chars=%s transcode_ok=%s stt_provider=%s stt_language=%s",
            session_id,
            len(transcript),
            transcode_ok,
            stt_provider,
            stt_language,
        )

        answer_value = str(answer).strip() if answer is not None else ""
        if answer_value:
            # Voice note carries a low-rating reason: submit the chosen rating with the
            # spoken transcript as the reason and advance the flow.
            return {
                "transcript": transcript,
                **FeedbackWebSurveyService.submit_answer(
                    db,
                    session_id=session_id,
                    answer=answer_value,
                    reason=transcript,
                    reason_source="voice",
                ),
            }

        if mode == "transcribe":
            # Transcribe only: caller fills the answer box and submits via the answer route.
            return {"transcript": transcript}

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

        if mode == "reason_prev":
            steps = _web_steps(db, location)
            step_index = int(session.current_step or 0) - 1
            if step_index >= 0 and step_index < len(steps) and transcript:
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
        result = FeedbackWebSurveyService.submit_answer(
            db,
            session_id=session_id,
            answer=transcript,
            answer_source="voice",
            source_language=stt_language,
        )
        return {"transcript": transcript, "saved": True, **result}

    @staticmethod
    def session_status(db: Session, session_id: str) -> dict[str, Any]:
        """Lightweight poll for tell-us-more deadline auto-advance on web clients."""
        session = db.get(FeedbackSession, session_id)
        if session is None or session.status != "active":
            return {"active": False, "completed": session is not None and session.status == "completed"}
        location = db.get(FeedbackLocation, session.location_id)
        if location is None:
            raise ValueError("Location not found")
        steps = _web_steps(db, location)
        state = load_feedback_session_state(session)
        step_index = int(session.current_step or 0)
        deadline = parse_deadline(state) if is_tell_us_more_pending(state) else None
        question = (
            _step_to_question(db, location, steps[step_index], language=session.detected_language)
            if step_index < len(steps)
            else None
        )
        return {
            "active": True,
            "completed": False,
            "step_index": step_index,
            "step_count": len(steps),
            "question": question,
            "pending_tell_us_more": is_tell_us_more_pending(state),
            "deadline_at": deadline.isoformat() if deadline else None,
        }
