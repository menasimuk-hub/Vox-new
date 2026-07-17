"""Customer Feedback WhatsApp conversation handler."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import (
    FeedbackLocation,
    FeedbackMarketingSubscriber,
    FeedbackResponse,
    FeedbackSession,
    FeedbackWaTemplate,
)
from app.services.customer_feedback.billing_service import FeedbackBillingService
from app.services.customer_feedback.feedback_answer_service import (
    is_negative_topic_answer,
    is_opt_in_yes,
    translate_answer_to_english,
)
from app.services.customer_feedback.locale_service import resolve_session_language
from app.services.customer_feedback.feedback_wa_send_service import FeedbackWaSendService
from app.services.customer_feedback.location_service import FeedbackLocationService, SCAN_QR_HINT
from app.services.customer_feedback.feedback_wa_session_state import (
    clear_tell_us_more_pending,
    is_tell_us_more_pending,
    load_feedback_session_state,
    save_feedback_session_state,
    set_tell_us_more_pending,
)
from app.services.customer_feedback.survey_config_service import (
    format_template_message,
    get_system_template,
    load_survey_config,
    repair_survey_config_if_needed,
    template_for_step,
)


logger = logging.getLogger(__name__)

# Mirror Telnyx's profile-level opt-out keywords. Telnyx blocks the whole platform
# number for any of these; we deactivate the phone's promo subscriptions to match.
STOP_WORDS = frozenset(
    {
        "stop",
        "stop all",
        "stopall",
        "unsubscribe",
        "unsubscribe all",
        "opt out",
        "opt-out",
        "opt out all",
        "opt-out all",
        "cancel",
        "end",
        "quit",
        "إيقاف",
        "الغاء",
    }
)


class FeedbackWhatsappService:
    @staticmethod
    def _send_wa(
        db: Session,
        *,
        to_number: str,
        body: str,
        org_id: str | None,
        tpl: FeedbackWaTemplate | None = None,
        location: FeedbackLocation | None = None,
        require_template: bool = False,
    ) -> bool:
        result = FeedbackWaSendService.send_plain_or_template(
            db,
            to_number=to_number,
            body=body,
            org_id=org_id,
            tpl=tpl,
            location=location,
            require_template=require_template,
        )
        if not result.ok:
            logger.warning(
                "feedback_wa_reply_failed to=%s status=%s detail=%s org_id=%s template_key=%s",
                to_number,
                result.status,
                result.detail,
                org_id,
                tpl.template_key if tpl else None,
            )
        return result.ok

    @staticmethod
    def try_handle_inbound(
        db: Session,
        *,
        from_phone: str,
        body: str,
        org_id: str | None = None,
        record: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_body = str(body or "").strip()
        answer_source = "text"
        source_language: str | None = None
        if not normalized_body:
            from app.services.customer_feedback.feedback_voice_service import is_voice_inbound

            if is_voice_inbound(record):
                session = FeedbackWhatsappService._active_session(db, from_phone=from_phone)
                if session is None:
                    return {"handled": False, "reason": "voice_no_session"}
                return FeedbackWhatsappService._handle_voice_inbound_async(
                    db,
                    session=session,
                    record=record or {},
                )

        body_lower = normalized_body.lower().strip()
        if body_lower in STOP_WORDS:
            # Telnyx applies its own block rule at the messaging-profile level for
            # STOP-family keywords, which blocks this number across every business
            # sharing the platform sender. We mirror that here: opt the phone out of
            # all promo subscriptions so our records match Telnyx's behaviour.
            return FeedbackWhatsappService._handle_stop(db, from_phone=from_phone)

        token = FeedbackLocationService.parse_trigger_ref(normalized_body)
        if token:
            location = FeedbackLocationService.resolve_by_token(db, token)
            if location is None:
                return {"handled": False, "reason": "unknown_token", "token": token}
            lang_hint = FeedbackLocationService.parse_trigger_language_hint(normalized_body)
            return FeedbackWhatsappService._start_session(
                db,
                location=location,
                from_phone=from_phone,
                token=token,
                language_hint=lang_hint,
            )

        session = FeedbackWhatsappService._active_session(db, from_phone=from_phone)
        if session is None:
            if FeedbackLocationService.is_feedback_intent_message(normalized_body):
                FeedbackWhatsappService._send_wa(
                    db,
                    to_number=from_phone,
                    body=SCAN_QR_HINT,
                    org_id=org_id,
                )
                return {"handled": True, "reason": "missing_token"}
            return {"handled": False, "reason": "no_session"}
        return FeedbackWhatsappService._advance_session(
            db,
            session=session,
            answer=normalized_body,
            answer_source=answer_source,
            source_language=source_language,
        )

    @staticmethod
    def _handle_stop(db: Session, *, from_phone: str) -> dict[str, Any]:
        # Telnyx already blocks this number profile-wide for STOP keywords, so we
        # deactivate every active promo subscription for the phone to stay in sync.
        # Also record org-level opt-outs so admin STOP list stays complete.
        from app.services.org_opt_out_service import OrgOptOutService

        rows = list(
            db.execute(
                select(FeedbackMarketingSubscriber).where(
                    FeedbackMarketingSubscriber.phone_e164 == from_phone,
                    FeedbackMarketingSubscriber.is_active.is_(True),
                )
            )
            .scalars()
            .all()
        )
        session = FeedbackWhatsappService._active_session(db, from_phone=from_phone)
        org_ids: set[str] = {str(r.org_id) for r in rows if r.org_id}
        if session is not None and session.org_id:
            org_ids.add(str(session.org_id))

        now = datetime.utcnow()
        for row in rows:
            row.is_active = False
            row.opted_out_at = now
            db.add(row)
        if rows:
            db.commit()

        for org_id in org_ids:
            try:
                OrgOptOutService.add_opt_out(
                    db,
                    org_id=org_id,
                    phone=from_phone,
                    reason="whatsapp_keyword_opt_out",
                )
            except Exception:
                logger.exception("feedback_opt_out_org_record_failed org=%s", org_id)

        if org_ids:
            reply_org = str(rows[0].org_id) if rows else next(iter(org_ids))
            FeedbackWhatsappService._send_wa(
                db,
                to_number=from_phone,
                body="You have been unsubscribed from promotional messages.",
                org_id=reply_org,
            )
            return {"handled": True, "opted_out": True}
        return {"handled": False, "reason": "no_subscriber"}

    @staticmethod
    def _active_session(db: Session, *, from_phone: str) -> FeedbackSession | None:
        cutoff = datetime.utcnow() - timedelta(hours=24)
        return db.execute(
            select(FeedbackSession)
            .where(
                FeedbackSession.visitor_phone == from_phone,
                FeedbackSession.status == "active",
                FeedbackSession.started_at >= cutoff,
            )
            .order_by(FeedbackSession.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def _steps_for_location(db: Session, location: FeedbackLocation) -> list[dict[str, Any]]:
        from app.services.customer_feedback.feedback_marketing_policy import filter_survey_steps

        config = load_survey_config(db, location)
        steps = filter_survey_steps(config.get("steps") or [])
        if steps:
            return steps
        tpl = db.execute(
            select(FeedbackWaTemplate)
            .where(FeedbackWaTemplate.survey_type_id == location.survey_type_id, FeedbackWaTemplate.is_active.is_(True))
            .limit(1)
        ).scalar_one_or_none()
        if tpl:
            return [{"kind": "topic", "survey_type_id": location.survey_type_id, "template_key": tpl.template_key}]
        return [{"kind": "topic", "survey_type_id": location.survey_type_id, "template_key": "fallback"}]

    @staticmethod
    def _start_session(
        db: Session,
        *,
        location,
        from_phone: str,
        token: str,
        language_hint: str | None = None,
    ) -> dict[str, Any]:
        dedupe_key = f"{from_phone}:{token}"
        recent = db.execute(
            select(FeedbackSession)
            .where(FeedbackSession.trigger_dedupe_key == dedupe_key)
            .order_by(FeedbackSession.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if recent and recent.started_at and recent.started_at >= datetime.utcnow() - timedelta(seconds=60):
            if recent.status == "active":
                return {"handled": True, "session_id": recent.id, "deduped": True, "org_id": location.org_id}

        ok, reason = FeedbackBillingService.ensure_units_available(db, location.org_id)
        if not ok:
            FeedbackWhatsappService._send_wa(
                db,
                to_number=from_phone,
                body=reason or "Customer feedback is unavailable right now.",
                org_id=location.org_id,
            )
            return {"handled": True, "reason": "units_exhausted", "org_id": location.org_id}

        FeedbackLocationService.record_scan(db, location)
        repair_survey_config_if_needed(db, location)
        now = datetime.utcnow()
        session = FeedbackSession(
            id=str(uuid.uuid4()),
            org_id=location.org_id,
            location_id=location.id,
            visitor_phone=from_phone,
            status="active",
            current_step=0,
            detected_language=resolve_session_language(
                phone=from_phone,
                trigger_hint=language_hint,
                location_country=getattr(location, "wa_sender_country", None),
            ),
            trigger_dedupe_key=dedupe_key,
            started_at=now,
            created_at=now,
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        steps = FeedbackWhatsappService._steps_for_location(db, location)
        if not steps:
            logger.error(
                "feedback_wa_no_steps location_id=%s industry_id=%s survey_type_id=%s",
                location.id,
                location.industry_id,
                location.survey_type_id,
            )
            session.status = "failed"
            db.add(session)
            db.commit()
            return {"handled": True, "reason": "missing_steps", "org_id": location.org_id}

        first_step = steps[0]
        tpl = template_for_step(db, location, first_step, language=session.detected_language)
        if tpl is None:
            logger.error(
                "feedback_wa_no_template location_id=%s industry_id=%s step=%s language=%s",
                location.id,
                location.industry_id,
                first_step,
                session.detected_language,
            )
            session.status = "failed"
            db.add(session)
            db.commit()
            return {"handled": True, "reason": "missing_template", "org_id": location.org_id}

        message = format_template_message(tpl)
        sent = FeedbackWhatsappService._send_wa(
            db,
            to_number=from_phone,
            body=message,
            org_id=location.org_id,
            tpl=tpl,
            location=location,
            require_template=True,
        )
        if not sent:
            session.status = "failed"
            db.add(session)
            db.commit()
            return {"handled": True, "reason": "send_failed", "org_id": location.org_id}

        FeedbackBillingService.consume_unit(db, location.org_id)
        session.units_charged = True
        db.add(session)
        db.commit()
        return {
            "handled": True,
            "session_id": session.id,
            "org_id": location.org_id,
            "template_sent": sent,
            "template_key": tpl.template_key,
        }

    @staticmethod
    def _save_answer(
        db: Session,
        *,
        session: FeedbackSession,
        location: FeedbackLocation,
        step: dict[str, Any],
        tpl: FeedbackWaTemplate | None,
        answer: str,
        step_index: int,
        answer_source: str = "text",
        source_language: str | None = None,
    ) -> None:
        original = str(answer or "").strip()
        translated = translate_answer_to_english(
            db,
            answer=original,
            detected_language=session.detected_language,
            tpl=tpl,
            source_language=source_language,
        )
        answer_en = str(translated.get("answer_text_en") or original)
        survey_type_id = str(step.get("survey_type_id") or location.survey_type_id)
        db.add(
            FeedbackResponse(
                id=str(uuid.uuid4()),
                session_id=session.id,
                org_id=session.org_id,
                location_id=session.location_id,
                survey_type_id=survey_type_id,
                question_key=(tpl.template_key if tpl else str(step.get("template_key") or step.get("kind"))),
                answer_text=answer_en,
                original_text=original,
                answer_text_en=answer_en,
                translation_status=str(translated.get("translation_status") or "") or None,
                transcription_status=None,
                detected_language=source_language or session.detected_language,
                step_order=step_index + 1,
                answer_source=answer_source or "text",
                created_at=datetime.utcnow(),
            )
        )

    @staticmethod
    def _save_tell_us_more_answer(
        db: Session,
        *,
        session: FeedbackSession,
        location: FeedbackLocation,
        step_index: int,
        topic_key: str,
        survey_type_id: str,
        answer: str,
        answer_source: str,
        source_language: str | None = None,
    ) -> bool:
        original = str(answer or "").strip()
        if not original or original.lower() == "skip":
            return False
        translated = translate_answer_to_english(
            db,
            answer=original,
            detected_language=session.detected_language,
            tpl=None,
            source_language=source_language,
        )
        answer_en = str(translated.get("answer_text_en") or original)
        db.add(
            FeedbackResponse(
                id=str(uuid.uuid4()),
                session_id=session.id,
                org_id=session.org_id,
                location_id=session.location_id,
                survey_type_id=survey_type_id,
                question_key=f"{topic_key}__tell_us_more",
                answer_text=answer_en,
                original_text=original,
                answer_text_en=answer_en,
                translation_status=str(translated.get("translation_status") or "") or None,
                transcription_status=None,
                detected_language=source_language or session.detected_language,
                step_order=step_index + 1,
                answer_source=answer_source or "text",
                created_at=datetime.utcnow(),
            )
        )
        return True

    @staticmethod
    def _handle_voice_inbound_async(
        db: Session,
        *,
        session: FeedbackSession,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        """Accept WA voice, save pending response, enqueue Celery STT+translate, advance flow."""
        from app.services.customer_feedback.feedback_voice_note_service import (
            create_pending_response_and_job,
            enqueue_feedback_voice_job,
            extract_wa_media,
        )

        location = db.get(FeedbackLocation, session.location_id)
        if location is None:
            return {"handled": True, "reason": "missing_location"}

        media = extract_wa_media(record)
        if not media.get("media_url"):
            FeedbackWhatsappService._send_wa(
                db,
                to_number=session.visitor_phone,
                body="Sorry, I couldn't receive that voice note. Please try again or type your reply.",
                org_id=session.org_id,
            )
            return {"handled": True, "reason": "voice_no_media"}

        state = load_feedback_session_state(session)
        if is_tell_us_more_pending(state):
            step_index = int(state.get("tell_us_more_step_index") or session.current_step or 0)
            topic_key = str(state.get("tell_us_more_topic_key") or "topic")
            survey_type_id = str(state.get("tell_us_more_survey_type_id") or location.survey_type_id)
            question_key = f"{topic_key}__tell_us_more"
            _response, job = create_pending_response_and_job(
                db,
                session=session,
                location_id=session.location_id,
                survey_type_id=survey_type_id,
                question_key=question_key,
                step_order=step_index + 1,
                media_url=media["media_url"],
                audio_mime_type=media.get("mime_type") or None,
                inbound_message_id=media.get("inbound_message_id") or "",
                provider_media_id=media.get("provider_media_id") or "",
            )
            clear_tell_us_more_pending(state)
            save_feedback_session_state(session, state)
            session.current_step = step_index + 1
            db.add(session)
            db.commit()
            enqueue_feedback_voice_job(job.id)
            FeedbackWhatsappService._send_wa(
                db,
                to_number=session.visitor_phone,
                body="Thanks — we got your voice note and are processing it.",
                org_id=session.org_id,
                location=location,
            )
            return FeedbackWhatsappService._continue_after_step(db, session=session)

        steps = FeedbackWhatsappService._steps_for_location(db, location)
        step_index = int(session.current_step or 0)
        if step_index >= len(steps):
            return FeedbackWhatsappService._continue_after_step(db, session=session)
        current_step = steps[step_index]
        tpl = template_for_step(db, location, current_step, language=session.detected_language)
        survey_type_id = str(current_step.get("survey_type_id") or location.survey_type_id)
        question_key = tpl.template_key if tpl else str(current_step.get("template_key") or current_step.get("kind"))
        _response, job = create_pending_response_and_job(
            db,
            session=session,
            location_id=session.location_id,
            survey_type_id=survey_type_id,
            question_key=question_key,
            step_order=step_index + 1,
            media_url=media["media_url"],
            audio_mime_type=media.get("mime_type") or None,
            inbound_message_id=media.get("inbound_message_id") or "",
            provider_media_id=media.get("provider_media_id") or "",
        )
        session.current_step = step_index + 1
        db.add(session)
        db.commit()
        enqueue_feedback_voice_job(job.id)
        FeedbackWhatsappService._send_wa(
            db,
            to_number=session.visitor_phone,
            body="Thanks — we got your voice note and are processing it.",
            org_id=session.org_id,
            location=location,
        )
        return FeedbackWhatsappService._continue_after_step(db, session=session)

    @staticmethod
    def _continue_after_step(db: Session, *, session: FeedbackSession) -> dict[str, Any]:
        location = db.get(FeedbackLocation, session.location_id)
        if location is None:
            session.status = "failed"
            db.add(session)
            db.commit()
            return {"handled": True, "reason": "missing_location"}

        steps = FeedbackWhatsappService._steps_for_location(db, location)
        if int(session.current_step or 0) >= len(steps):
            session.status = "completed"
            session.completed_at = datetime.utcnow()
            db.add(session)
            db.commit()
            from app.services.customer_feedback.feedback_ai_followup_service import schedule_if_eligible

            try:
                schedule_if_eligible(db, session=session, location=location)
            except Exception:
                logger.exception("feedback_ai_followup_schedule_failed session_id=%s", session.id)
            thank_tpl = get_system_template(db, "thank_you", language=session.detected_language)
            thank_body = thank_tpl.body_text if thank_tpl else "Thank you — your feedback has been recorded."
            sent = FeedbackWhatsappService._send_wa(
                db,
                to_number=session.visitor_phone,
                body=thank_body,
                org_id=session.org_id,
                tpl=thank_tpl,
                location=location,
                require_template=thank_tpl is not None,
            )
            if not sent and thank_body:
                logger.error(
                    "feedback_wa_thank_you_failed session_id=%s location_id=%s",
                    session.id,
                    location.id,
                )
                FeedbackWhatsappService._send_wa(
                    db,
                    to_number=session.visitor_phone,
                    body=thank_body,
                    org_id=session.org_id,
                    tpl=None,
                    location=location,
                    require_template=False,
                )
            return {"handled": True, "completed": True}

        next_step = steps[int(session.current_step or 0)]
        next_tpl = template_for_step(db, location, next_step, language=session.detected_language)
        if next_tpl is None:
            logger.error(
                "feedback_wa_no_template location_id=%s step=%s language=%s session_id=%s",
                location.id,
                next_step,
                session.detected_language,
                session.id,
            )
            return {"handled": True, "reason": "missing_template", "session_id": session.id}
        next_message = format_template_message(next_tpl)
        FeedbackWhatsappService._send_wa(
            db,
            to_number=session.visitor_phone,
            body=next_message,
            org_id=session.org_id,
            tpl=next_tpl,
            location=location,
            require_template=True,
        )
        return {"handled": True, "session_id": session.id}

    @staticmethod
    def _advance_session(
        db: Session,
        *,
        session: FeedbackSession,
        answer: str,
        answer_source: str = "text",
        source_language: str | None = None,
    ) -> dict[str, Any]:
        location = db.get(FeedbackLocation, session.location_id)
        if location is None:
            session.status = "failed"
            db.add(session)
            db.commit()
            return {"handled": True, "reason": "missing_location"}

        state = load_feedback_session_state(session)
        if is_tell_us_more_pending(state):
            step_index = int(state.get("tell_us_more_step_index") or session.current_step or 0)
            clean = str(answer or "").strip()
            if clean.lower() == "skip":
                clear_tell_us_more_pending(state)
                save_feedback_session_state(session, state)
                session.current_step = step_index + 1
                db.add(session)
                db.commit()
                return FeedbackWhatsappService._continue_after_step(db, session=session)
            if not clean:
                FeedbackWhatsappService._send_wa(
                    db,
                    to_number=session.visitor_phone,
                    body="Please type or send a voice note with a bit more detail, or reply Skip to continue.",
                    org_id=session.org_id,
                    tpl=None,
                    location=location,
                )
                return {"handled": True, "awaiting_tell_us_more": True, "session_id": session.id}
            saved = FeedbackWhatsappService._save_tell_us_more_answer(
                db,
                session=session,
                location=location,
                step_index=step_index,
                topic_key=str(state.get("tell_us_more_topic_key") or "topic"),
                survey_type_id=str(state.get("tell_us_more_survey_type_id") or location.survey_type_id),
                answer=clean,
                answer_source=answer_source,
                source_language=source_language,
            )
            if not saved:
                FeedbackWhatsappService._send_wa(
                    db,
                    to_number=session.visitor_phone,
                    body="Please type or send a voice note with a bit more detail, or reply Skip to continue.",
                    org_id=session.org_id,
                    tpl=None,
                    location=location,
                )
                return {"handled": True, "awaiting_tell_us_more": True, "session_id": session.id}
            clear_tell_us_more_pending(state)
            save_feedback_session_state(session, state)
            session.current_step = step_index + 1
            db.add(session)
            db.commit()
            return FeedbackWhatsappService._continue_after_step(db, session=session)

        steps = FeedbackWhatsappService._steps_for_location(db, location)
        step_index = int(session.current_step or 0)
        if step_index >= len(steps):
            return FeedbackWhatsappService._continue_after_step(db, session=session)

        current_step = steps[step_index]
        tpl = template_for_step(db, location, current_step, language=session.detected_language)
        step_kind = str(current_step.get("kind") or "topic")
        clean_answer = str(answer or "").strip()

        if step_kind == "open_question" and not clean_answer:
            FeedbackWhatsappService._send_wa(
                db,
                to_number=session.visitor_phone,
                body="Please share your feedback as a message or voice note, or reply Skip to continue.",
                org_id=session.org_id,
                tpl=None,
                location=location,
            )
            return {"handled": True, "session_id": session.id}

        if step_kind == "open_question" and clean_answer.lower() == "skip":
            session.current_step = step_index + 1
            db.add(session)
            db.commit()
            return FeedbackWhatsappService._continue_after_step(db, session=session)

        if current_step.get("kind") == "marketing_opt_in":
            if is_opt_in_yes(
                db,
                answer=answer,
                tpl=tpl,
                detected_language=session.detected_language,
            ):
                existing = db.execute(
                    select(FeedbackMarketingSubscriber).where(
                        FeedbackMarketingSubscriber.org_id == session.org_id,
                        FeedbackMarketingSubscriber.phone_e164 == session.visitor_phone,
                    ).limit(1)
                ).scalar_one_or_none()
                if existing:
                    existing.is_active = True
                    existing.opted_out_at = None
                    existing.opted_in_at = datetime.utcnow()
                    existing.location_id = session.location_id
                    existing.session_id = session.id
                    db.add(existing)
                else:
                    db.add(
                        FeedbackMarketingSubscriber(
                            id=str(uuid.uuid4()),
                            org_id=session.org_id,
                            location_id=session.location_id,
                            session_id=session.id,
                            phone_e164=session.visitor_phone,
                            consent_version="v1",
                            opted_in_at=datetime.utcnow(),
                            is_active=True,
                            created_at=datetime.utcnow(),
                        )
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
        else:
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
            if (
                current_step.get("kind") == "topic"
                and is_negative_topic_answer(
                    db,
                    answer=answer,
                    tpl=tpl,
                    detected_language=session.detected_language,
                )
            ):
                tell_more = get_system_template(db, "tell_us_more", language=session.detected_language)
                if tell_more:
                    set_tell_us_more_pending(
                        state,
                        step_index=step_index,
                        topic_key=str(tpl.template_key if tpl else "topic"),
                        survey_type_id=str(current_step.get("survey_type_id") or location.survey_type_id),
                    )
                    save_feedback_session_state(session, state)
                    db.add(session)
                    db.commit()
                    FeedbackWhatsappService._send_wa(
                        db,
                        to_number=session.visitor_phone,
                        body=tell_more.body_text,
                        org_id=session.org_id,
                        tpl=tell_more,
                        location=location,
                        require_template=True,
                    )
                    return {"handled": True, "awaiting_tell_us_more": True, "session_id": session.id}

        session.current_step = step_index + 1
        db.add(session)
        db.commit()
        return FeedbackWhatsappService._continue_after_step(db, session=session)
