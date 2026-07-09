"""Schedule and dispatch AI voice follow-up for unhappy Customer Feedback respondents."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackLocation, FeedbackResponse, FeedbackSession

logger = logging.getLogger(__name__)

LOW_ANSWERS = frozenset({"poor", "bad", "no", "maybe", "slow", "avg"})


def parse_ai_follow_up_config(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            cfg = parsed.get("ai_follow_up")
            return cfg if isinstance(cfg, dict) else {}
    except json.JSONDecodeError:
        pass
    return {}


def load_ai_follow_up_from_location(location: FeedbackLocation) -> dict[str, Any]:
    raw = getattr(location, "survey_config_json", None)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            cfg = parsed.get("ai_follow_up")
            return cfg if isinstance(cfg, dict) else {}
    except json.JSONDecodeError:
        return {}
    return {}


def _has_written_reason(db: Session, session_id: str) -> bool:
    rows = db.execute(
        select(FeedbackResponse).where(FeedbackResponse.session_id == session_id)
    ).scalars().all()
    for row in rows:
        key = str(row.question_key or "")
        text = str(row.answer_text or row.original_text or "").strip()
        if not text or text.lower() == "skip":
            continue
        if key.endswith("__low_reason") or "tell_us_more" in key or row.answer_source == "voice":
            return True
        if len(text) >= 8:
            return True
    return False


def _had_low_rating(db: Session, session_id: str) -> bool:
    rows = db.execute(
        select(FeedbackResponse).where(FeedbackResponse.session_id == session_id)
    ).scalars().all()
    for row in rows:
        val = str(row.answer_text or row.original_text or "").strip().lower()
        if val in LOW_ANSWERS or "poor" in val:
            return True
    return False


def _callable_phone(visitor_phone: str) -> bool:
    phone = str(visitor_phone or "").strip()
    return bool(phone) and not phone.startswith("web:")


def _build_followup_instructions(job, *, org_name: str) -> tuple[str, str]:
    context = str(job.business_context or "").strip()
    promo = ""
    if job.promo_enabled and job.promo_code:
        promo = (
            f"\nIf the customer is receptive, you may offer promo code {job.promo_code}"
            f" ({job.promo_description or 'recovery offer'}). Only mention it once."
        )
    instructions = (
        "You are calling a customer who left a low rating in a feedback survey but did not explain why.\n"
        f"Business: {org_name}\n"
        f"Context from the venue:\n{context or 'General service recovery call.'}\n"
        "Goals: apologise sincerely, ask what went wrong, listen, summarise, and thank them."
        " Keep the call under 3 minutes. Speak English only."
        f"{promo}"
    )
    greeting = (
        f"Hi, this is a quick follow-up from {org_name}. "
        "You recently shared feedback with us and we wanted to understand how we can do better. "
        "Do you have a minute?"
    )
    return greeting, instructions


def _resolve_survey_assistant(db: Session, org_id: str) -> tuple[str, Any | None]:
    from app.core.config import get_settings
    from app.core.agent_services import SERVICE_SURVEY
    from app.models.agent import AgentDefinition
    from app.services.agent_service_resolver import resolve_agent_for_org_service
    from app.services.telnyx_assistant_service import normalize_telnyx_assistant_id

    agent = resolve_agent_for_org_service(db, org_id=org_id, service_key=SERVICE_SURVEY, require_active=True)
    if agent and str(agent.telnyx_assistant_id or "").strip():
        return normalize_telnyx_assistant_id(agent.telnyx_assistant_id), agent

    default = db.execute(
        select(AgentDefinition)
        .where(
            AgentDefinition.is_active.is_(True),
            AgentDefinition.supports_survey.is_(True),
            AgentDefinition.is_default_survey.is_(True),
        )
        .limit(1)
    ).scalar_one_or_none()
    if default and str(default.telnyx_assistant_id or "").strip():
        return normalize_telnyx_assistant_id(default.telnyx_assistant_id), default

    configured = str(get_settings().survey_telnyx_assistant_id or "").strip()
    if configured:
        return normalize_telnyx_assistant_id(configured), agent
    return "", agent


def schedule_if_eligible(db: Session, *, session: FeedbackSession, location: FeedbackLocation) -> bool:
    """Enqueue AI follow-up when config enabled and respondent is eligible."""
    cfg = load_ai_follow_up_from_location(location)
    if not cfg.get("enabled"):
        return False
    if not _callable_phone(session.visitor_phone):
        return False
    if not _had_low_rating(db, session.id):
        return False
    if _has_written_reason(db, session.id):
        return False

    delay_hours = int(cfg.get("delay_hours") or 24)
    if delay_hours not in (24, 48):
        delay_hours = 24
    scheduled_at = datetime.now(timezone.utc) + timedelta(hours=delay_hours)

    from app.models.customer_feedback import FeedbackAiFollowUpJob

    existing = db.execute(
        select(FeedbackAiFollowUpJob).where(FeedbackAiFollowUpJob.session_id == session.id)
    ).scalar_one_or_none()
    if existing is not None:
        return False

    job = FeedbackAiFollowUpJob(
        id=str(uuid.uuid4()),
        org_id=session.org_id,
        location_id=session.location_id,
        session_id=session.id,
        visitor_phone=session.visitor_phone,
        business_context=str(cfg.get("business_context") or cfg.get("businessContext") or "").strip(),
        promo_enabled=bool(cfg.get("promo_enabled") or cfg.get("promoEnabled")),
        promo_code=str(cfg.get("promo_code") or cfg.get("promoCode") or "").strip(),
        promo_description=str(cfg.get("promo_description") or cfg.get("promoDescription") or "").strip(),
        scheduled_at=scheduled_at.replace(tzinfo=None),
        status="scheduled",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    logger.info(
        "feedback_ai_followup_scheduled session_id=%s scheduled_at=%s",
        session.id,
        scheduled_at.isoformat(),
    )
    return True


def process_due_jobs(db: Session, *, limit: int = 20) -> int:
    """Process due AI follow-up jobs. Returns count dispatched."""
    from app.models.customer_feedback import FeedbackAiFollowUpJob

    now = datetime.utcnow()
    rows = db.execute(
        select(FeedbackAiFollowUpJob)
        .where(FeedbackAiFollowUpJob.status == "scheduled")
        .where(FeedbackAiFollowUpJob.scheduled_at <= now)
        .order_by(FeedbackAiFollowUpJob.scheduled_at.asc())
        .limit(limit)
    ).scalars().all()

    dispatched = 0
    for job in rows:
        try:
            call_id = _dispatch_job(db, job)
            job.status = "dispatched"
            job.call_id = call_id
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
            dispatched += 1
        except Exception:
            logger.exception("feedback_ai_followup_dispatch_failed job_id=%s", job.id)
            job.status = "failed"
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
    return dispatched


def _dispatch_job(db: Session, job) -> str | None:
    """Dial the respondent via Telnyx using the platform survey voice assistant."""
    from app.models.organisation import Organisation
    from app.services.telnyx_api_key import normalize_telnyx_e164, telnyx_outbound_caller_id
    from app.services.telnyx_phone_allowlist_service import TelnyxPhoneAllowlistService
    from app.services.telnyx_voice_service import TelnyxVoiceAdapter, _telnyx_config

    org = db.get(Organisation, job.org_id)
    org_name = str(org.name if org else "the business").strip() or "the business"
    assistant_id, agent = _resolve_survey_assistant(db, job.org_id)
    if not assistant_id:
        raise RuntimeError("No Telnyx survey assistant configured for AI follow-up calls")

    telnyx_config = _telnyx_config(db)
    from_number = telnyx_outbound_caller_id(telnyx_config)
    if not from_number:
        raise RuntimeError("Telnyx outbound caller ID is not configured")

    phone_check = TelnyxPhoneAllowlistService.validate_phone_db(db, str(job.visitor_phone or ""))
    if not phone_check.get("allowed"):
        raise RuntimeError(phone_check.get("reason") or "Phone number not allowed")

    greeting, instructions = _build_followup_instructions(job, org_name=org_name)
    to_number = normalize_telnyx_e164(str(job.visitor_phone or ""))

    result = TelnyxVoiceAdapter.start_outbound_call(
        to_number=to_number,
        from_number=from_number,
        config=telnyx_config,
        client_state={
            "feedback_ai_followup": True,
            "feedback_ai_followup_job_id": job.id,
            "org_id": job.org_id,
            "location_id": job.location_id,
            "session_id": job.session_id,
            "agent_id": agent.id if agent else None,
            "telnyx_assistant_id": assistant_id,
            "survey_greeting": greeting,
            "survey_instructions": instructions[:4000],
            "promo_enabled": bool(job.promo_enabled),
            "promo_code": job.promo_code,
            "promo_description": job.promo_description,
        },
    )
    if not result.ok or not result.external_id:
        raise RuntimeError(result.detail or result.status or "dial_failed")

    logger.info(
        "feedback_ai_followup_dialled job_id=%s call_id=%s org_id=%s",
        job.id,
        result.external_id,
        job.org_id,
    )
    return str(result.external_id)
