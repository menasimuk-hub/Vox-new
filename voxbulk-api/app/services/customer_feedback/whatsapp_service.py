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
from app.services.customer_feedback.survey_config_service import (
    format_template_message,
    get_system_template,
    load_survey_config,
    repair_survey_config_if_needed,
    template_for_step,
)

logger = logging.getLogger(__name__)

STOP_WORDS = frozenset({"stop", "unsubscribe", "opt out", "opt-out", "إيقاف", "الغاء"})


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
        if not normalized_body:
            from app.services.customer_feedback.feedback_voice_service import is_voice_inbound, transcribe_inbound

            if is_voice_inbound(record):
                session = FeedbackWhatsappService._active_session(db, from_phone=from_phone)
                lang = session.detected_language if session else None
                transcript, ok = transcribe_inbound(
                    db,
                    record=record or {},
                    customer_phone=from_phone,
                    language=lang,
                )
                if ok and transcript:
                    normalized_body = transcript
                    answer_source = "voice"
                elif session:
                    FeedbackWhatsappService._send_wa(
                        db,
                        to_number=from_phone,
                        body="Sorry, I couldn't hear that clearly. Please try again or type your reply.",
                        org_id=session.org_id,
                    )
                    return {"handled": True, "reason": "voice_unclear"}
                else:
                    return {"handled": False, "reason": "voice_no_session"}

        if normalized_body.lower() in STOP_WORDS:
            return FeedbackWhatsappService._handle_stop(db, from_phone=from_phone, org_id=org_id)

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
        )

    @staticmethod
    def _handle_stop(db: Session, *, from_phone: str, org_id: str | None) -> dict[str, Any]:
        q = select(FeedbackMarketingSubscriber).where(
            FeedbackMarketingSubscriber.phone_e164 == from_phone,
            FeedbackMarketingSubscriber.is_active.is_(True),
        )
        if org_id:
            q = q.where(FeedbackMarketingSubscriber.org_id == org_id)
        rows = list(db.execute(q).scalars().all())
        now = datetime.utcnow()
        for row in rows:
            row.is_active = False
            row.opted_out_at = now
            db.add(row)
        if rows:
            db.commit()
            FeedbackWhatsappService._send_wa(
                db,
                to_number=from_phone,
                body="You have been unsubscribed from promotional messages.",
                org_id=org_id or rows[0].org_id,
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
        config = load_survey_config(db, location)
        steps = config.get("steps") or []
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
            detected_language=resolve_session_language(phone=from_phone, trigger_hint=language_hint),
            trigger_dedupe_key=dedupe_key,
            started_at=now,
            created_at=now,
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        FeedbackBillingService.consume_unit(db, location.org_id)
        session.units_charged = True
        db.add(session)
        db.commit()

        steps = FeedbackWhatsappService._steps_for_location(db, location)
        if not steps:
            logger.error(
                "feedback_wa_no_steps location_id=%s industry_id=%s survey_type_id=%s",
                location.id,
                location.industry_id,
                location.survey_type_id,
            )
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
    ) -> None:
        original = str(answer or "").strip()
        translated = translate_answer_to_english(
            db,
            answer=original,
            detected_language=session.detected_language,
            tpl=tpl,
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
                step_order=step_index + 1,
                answer_source=answer_source or "text",
                created_at=datetime.utcnow(),
            )
        )

    @staticmethod
    def _advance_session(
        db: Session,
        *,
        session: FeedbackSession,
        answer: str,
        answer_source: str = "text",
    ) -> dict[str, Any]:
        location = db.get(FeedbackLocation, session.location_id)
        if location is None:
            session.status = "failed"
            db.add(session)
            db.commit()
            return {"handled": True, "reason": "missing_location"}

        steps = FeedbackWhatsappService._steps_for_location(db, location)
        step_index = int(session.current_step or 0)
        if step_index >= len(steps):
            session.status = "completed"
            session.completed_at = datetime.utcnow()
            db.add(session)
            db.commit()
            return {"handled": True, "completed": True}

        current_step = steps[step_index]
        tpl = template_for_step(db, location, current_step, language=session.detected_language)

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
                    FeedbackWhatsappService._send_wa(
                        db,
                        to_number=session.visitor_phone,
                        body=tell_more.body_text,
                        org_id=session.org_id,
                        tpl=tell_more,
                        location=location,
                        require_template=True,
                    )

        session.current_step = step_index + 1
        db.add(session)
        db.commit()

        if session.current_step >= len(steps):
            session.status = "completed"
            session.completed_at = datetime.utcnow()
            db.add(session)
            db.commit()
            thank_tpl = get_system_template(db, "thank_you", language=session.detected_language)
            thank_body = thank_tpl.body_text if thank_tpl else "Thank you — your feedback has been recorded."
            FeedbackWhatsappService._send_wa(
                db,
                to_number=session.visitor_phone,
                body=thank_body,
                org_id=session.org_id,
                tpl=thank_tpl,
                location=location,
                require_template=thank_tpl is not None,
            )
            return {"handled": True, "completed": True}

        next_step = steps[session.current_step]
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
