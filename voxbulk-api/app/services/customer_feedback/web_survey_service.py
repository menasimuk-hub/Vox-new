"""Web survey sessions for Customer Feedback QR flows."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.customer_feedback import FeedbackIndustry, FeedbackLocation, FeedbackSession, FeedbackSurveyType
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


def _step_to_question(db: Session, location: FeedbackLocation, step: dict[str, Any], *, language: str | None) -> dict[str, Any]:
    kind = str(step.get("kind") or "topic")
    tpl = template_for_step(db, location, step, language=language)
    survey_type_id = str(step.get("survey_type_id") or location.survey_type_id or "")
    survey_type = db.get(FeedbackSurveyType, survey_type_id) if survey_type_id else None
    title = survey_type.name if survey_type else (tpl.template_key if tpl else kind)
    body = format_template_message(tpl) if tpl else title
    options = [
        {"label": "Excellent", "value": "Excellent"},
        {"label": "Good", "value": "Good"},
        {"label": "Poor", "value": "Poor"},
    ]
    if kind == "open_question":
        return {
            "kind": kind,
            "title": title,
            "body": body,
            "input": "text",
            "options": [],
            "allow_voice": True,
        }
    if kind == "tell_us_more":
        return {
            "kind": kind,
            "title": "Tell us more",
            "body": body or "What could we do better?",
            "input": "text",
            "options": [{"label": "Skip", "value": "skip"}],
            "allow_voice": True,
        }
    return {
        "kind": kind,
        "title": title,
        "body": body,
        "input": "choice",
        "options": options,
        "allow_voice": False,
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
        ok, reason = FeedbackBillingService.ensure_units_available(db, location.org_id)
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

        FeedbackBillingService.consume_unit(db, location.org_id)
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
    def submit_answer(
        db: Session,
        *,
        session_id: str,
        answer: str,
        answer_source: str = "text",
    ) -> dict[str, Any]:
        session = db.get(FeedbackSession, session_id)
        if session is None or session.status != "active":
            raise ValueError("Session not found or expired")
        if not str(session.visitor_phone or "").startswith("web:"):
            raise ValueError("Not a web survey session")

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
