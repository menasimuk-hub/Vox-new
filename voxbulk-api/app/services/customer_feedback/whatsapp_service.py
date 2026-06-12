"""Customer Feedback WhatsApp conversation handler."""

from __future__ import annotations

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
from app.services.customer_feedback.locale_service import detect_language_from_phone
from app.services.customer_feedback.location_service import FeedbackLocationService
from app.services.customer_feedback.survey_config_service import (
    format_template_message,
    load_survey_config,
    template_for_step,
)
from app.services.survey_wa_translation_service import SurveyWaTranslationService
from app.services.telnyx_messaging_service import TelnyxMessagingService

POOR_ANSWERS = frozenset({"poor", "unfriendly", "overpriced", "needs work", "too long", "slow", "unclear", "not for me", "unlikely", "no"})
OPT_IN_YES = frozenset({"yes", "yes please", "yes, please"})
OPT_IN_NO = frozenset({"no", "no thanks", "no thank you", "no, thanks"})
STOP_WORDS = frozenset({"stop", "unsubscribe", "opt out", "opt-out"})


class FeedbackWhatsappService:
    @staticmethod
    def try_handle_inbound(
        db: Session,
        *,
        from_phone: str,
        body: str,
        org_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_body = str(body or "").strip()
        if normalized_body.lower() in STOP_WORDS:
            return FeedbackWhatsappService._handle_stop(db, from_phone=from_phone, org_id=org_id)

        token = FeedbackLocationService.parse_trigger_ref(normalized_body)
        if token:
            location = FeedbackLocationService.resolve_by_token(db, token)
            if location is None:
                return {"handled": False, "reason": "unknown_token"}
            if org_id and location.org_id != org_id:
                return {"handled": False, "reason": "org_mismatch"}
            return FeedbackWhatsappService._start_session(db, location=location, from_phone=from_phone, token=token)

        session = FeedbackWhatsappService._active_session(db, from_phone=from_phone, org_id=org_id)
        if session is None:
            return {"handled": False, "reason": "no_session"}
        return FeedbackWhatsappService._advance_session(db, session=session, answer=normalized_body)

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
            TelnyxMessagingService.send_whatsapp(
                db,
                to=from_phone,
                body="You have been unsubscribed from promotional messages.",
                org_id=org_id or rows[0].org_id,
            )
            return {"handled": True, "opted_out": True}
        return {"handled": False, "reason": "no_subscriber"}

    @staticmethod
    def _active_session(db: Session, *, from_phone: str, org_id: str | None) -> FeedbackSession | None:
        cutoff = datetime.utcnow() - timedelta(hours=24)
        q = (
            select(FeedbackSession)
            .where(
                FeedbackSession.visitor_phone == from_phone,
                FeedbackSession.status == "active",
                FeedbackSession.started_at >= cutoff,
            )
            .order_by(FeedbackSession.started_at.desc())
            .limit(1)
        )
        if org_id:
            q = q.where(FeedbackSession.org_id == org_id)
        return db.execute(q).scalar_one_or_none()

    @staticmethod
    def _steps_for_location(db: Session, location: FeedbackLocation) -> list[dict[str, Any]]:
        config = load_survey_config(location)
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
    def _start_session(db: Session, *, location, from_phone: str, token: str) -> dict[str, Any]:
        dedupe_key = f"{from_phone}:{token}"
        recent = db.execute(
            select(FeedbackSession)
            .where(FeedbackSession.trigger_dedupe_key == dedupe_key)
            .order_by(FeedbackSession.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if recent and recent.started_at and recent.started_at >= datetime.utcnow() - timedelta(seconds=60):
            if recent.status == "active":
                return {"handled": True, "session_id": recent.id, "deduped": True}

        ok, reason = FeedbackBillingService.ensure_units_available(db, location.org_id)
        if not ok:
            TelnyxMessagingService.send_whatsapp(
                db,
                to=from_phone,
                body=reason or "Customer feedback is unavailable right now.",
                org_id=location.org_id,
            )
            return {"handled": True, "reason": "units_exhausted"}

        FeedbackLocationService.record_scan(db, location)
        now = datetime.utcnow()
        session = FeedbackSession(
            id=str(uuid.uuid4()),
            org_id=location.org_id,
            location_id=location.id,
            visitor_phone=from_phone,
            status="active",
            current_step=0,
            detected_language=detect_language_from_phone(from_phone),
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
            TelnyxMessagingService.send_whatsapp(
                db,
                to=from_phone,
                body="Thanks for your feedback! Reply with your rating from 1 (poor) to 5 (excellent).",
                org_id=location.org_id,
            )
            return {"handled": True, "session_id": session.id, "fallback": True}

        first_step = steps[0]
        tpl = template_for_step(db, location, first_step)
        message = format_template_message(tpl) if tpl else "Thanks for your feedback. Please reply to continue."
        TelnyxMessagingService.send_whatsapp(db, to=from_phone, body=message, org_id=location.org_id)
        return {"handled": True, "session_id": session.id}

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
    ) -> None:
        original = str(answer or "").strip()
        translated = SurveyWaTranslationService.translate_to_english(
            db, original, detected_language=session.detected_language
        )
        answer_en = str(translated.get("translated_text") or original)
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
                created_at=datetime.utcnow(),
            )
        )

    @staticmethod
    def _advance_session(db: Session, *, session: FeedbackSession, answer: str) -> dict[str, Any]:
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
        tpl = template_for_step(db, location, current_step)
        normalized = str(answer or "").strip().lower()

        if current_step.get("kind") == "marketing_opt_in":
            if normalized in OPT_IN_YES:
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
            )
            if (
                current_step.get("kind") == "topic"
                and normalized in POOR_ANSWERS
            ):
                tell_more = db.execute(
                    select(FeedbackWaTemplate).where(
                        FeedbackWaTemplate.template_key == "tell_us_more",
                        FeedbackWaTemplate.is_active.is_(True),
                    ).limit(1)
                ).scalar_one_or_none()
                if tell_more:
                    TelnyxMessagingService.send_whatsapp(
                        db,
                        to=session.visitor_phone,
                        body=tell_more.body_text,
                        org_id=session.org_id,
                    )

        session.current_step = step_index + 1
        db.add(session)
        db.commit()

        if session.current_step >= len(steps):
            session.status = "completed"
            session.completed_at = datetime.utcnow()
            db.add(session)
            db.commit()
            thank_tpl = db.execute(
                select(FeedbackWaTemplate).where(
                    FeedbackWaTemplate.template_key == "thank_you",
                    FeedbackWaTemplate.is_active.is_(True),
                ).limit(1)
            ).scalar_one_or_none()
            thank_body = thank_tpl.body_text if thank_tpl else "Thank you — your feedback has been recorded."
            TelnyxMessagingService.send_whatsapp(
                db,
                to=session.visitor_phone,
                body=thank_body,
                org_id=session.org_id,
            )
            return {"handled": True, "completed": True}

        next_step = steps[session.current_step]
        next_tpl = template_for_step(db, location, next_step)
        next_message = format_template_message(next_tpl) if next_tpl else "Please reply to continue."
        TelnyxMessagingService.send_whatsapp(
            db,
            to=session.visitor_phone,
            body=next_message,
            org_id=session.org_id,
        )
        return {"handled": True, "session_id": session.id}
