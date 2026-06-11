"""Customer Feedback WhatsApp conversation handler."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackLocation, FeedbackResponse, FeedbackSession, FeedbackWaTemplate
from app.services.customer_feedback.billing_service import FeedbackBillingService
from app.services.customer_feedback.location_service import FeedbackLocationService
from app.services.telnyx_messaging_service import TelnyxMessagingService


class FeedbackWhatsappService:
    @staticmethod
    def try_handle_inbound(
        db: Session,
        *,
        from_phone: str,
        body: str,
        org_id: str | None = None,
    ) -> dict[str, Any]:
        token = FeedbackLocationService.parse_trigger_ref(body)
        if token:
            location = FeedbackLocationService.resolve_by_token(db, token)
            if location is None:
                return {"handled": False, "reason": "unknown_token"}
            if org_id and location.org_id != org_id:
                return {"handled": False, "reason": "org_mismatch"}
            return FeedbackWhatsappService._start_session(db, location=location, from_phone=from_phone)

        session = FeedbackWhatsappService._active_session(db, from_phone=from_phone, org_id=org_id)
        if session is None:
            return {"handled": False, "reason": "no_session"}
        return FeedbackWhatsappService._advance_session(db, session=session, answer=body)

    @staticmethod
    def _active_session(db: Session, *, from_phone: str, org_id: str | None) -> FeedbackSession | None:
        q = (
            select(FeedbackSession)
            .where(
                FeedbackSession.visitor_phone == from_phone,
                FeedbackSession.status == "active",
            )
            .order_by(FeedbackSession.started_at.desc())
            .limit(1)
        )
        if org_id:
            q = q.where(FeedbackSession.org_id == org_id)
        return db.execute(q).scalar_one_or_none()

    @staticmethod
    def _templates_for_location(db: Session, location) -> list[FeedbackWaTemplate]:
        rows = list(
            db.execute(
                select(FeedbackWaTemplate)
                .where(
                    FeedbackWaTemplate.is_active.is_(True),
                    (FeedbackWaTemplate.survey_type_id == location.survey_type_id)
                    | (FeedbackWaTemplate.industry_id == location.industry_id),
                )
                .order_by(FeedbackWaTemplate.step_order)
            )
            .scalars()
            .all()
        )
        if rows:
            return rows
        return list(
            db.execute(
                select(FeedbackWaTemplate)
                .where(FeedbackWaTemplate.is_active.is_(True), FeedbackWaTemplate.industry_id.is_(None))
                .order_by(FeedbackWaTemplate.step_order)
            )
            .scalars()
            .all()
        )

    @staticmethod
    def _start_session(db: Session, *, location, from_phone: str) -> dict[str, Any]:
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
            started_at=now,
            created_at=now,
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        templates = FeedbackWhatsappService._templates_for_location(db, location)
        if not templates:
            welcome = "Thanks for your feedback! Reply with your rating from 1 (poor) to 5 (excellent)."
            TelnyxMessagingService.send_whatsapp(db, to=from_phone, body=welcome, org_id=location.org_id)
            return {"handled": True, "session_id": session.id, "fallback": True}

        first = templates[0]
        TelnyxMessagingService.send_whatsapp(db, to=from_phone, body=first.body_text, org_id=location.org_id)
        return {"handled": True, "session_id": session.id}

    @staticmethod
    def _advance_session(db: Session, *, session: FeedbackSession, answer: str) -> dict[str, Any]:
        location = db.get(FeedbackLocation, session.location_id)
        if location is None:
            session.status = "failed"
            db.add(session)
            db.commit()
            return {"handled": True, "reason": "missing_location"}

        templates = FeedbackWhatsappService._templates_for_location(db, location)
        step = int(session.current_step or 0)
        if step < len(templates):
            tpl = templates[step]
            db.add(
                FeedbackResponse(
                    id=str(uuid.uuid4()),
                    session_id=session.id,
                    org_id=session.org_id,
                    location_id=session.location_id,
                    survey_type_id=location.survey_type_id,
                    question_key=tpl.template_key,
                    answer_text=str(answer or "").strip(),
                    step_order=step + 1,
                    created_at=datetime.utcnow(),
                )
            )
            session.current_step = step + 1
            db.add(session)
            db.commit()

        if session.current_step >= len(templates):
            session.status = "completed"
            session.completed_at = datetime.utcnow()
            if not session.units_charged:
                FeedbackBillingService.consume_unit(db, session.org_id)
                session.units_charged = True
            db.add(session)
            db.commit()
            TelnyxMessagingService.send_whatsapp(
                db,
                to=session.visitor_phone,
                body="Thank you — your feedback has been recorded.",
                org_id=session.org_id,
            )
            return {"handled": True, "completed": True}

        next_tpl = templates[session.current_step]
        TelnyxMessagingService.send_whatsapp(
            db,
            to=session.visitor_phone,
            body=next_tpl.body_text,
            org_id=session.org_id,
        )
        return {"handled": True, "session_id": session.id}
