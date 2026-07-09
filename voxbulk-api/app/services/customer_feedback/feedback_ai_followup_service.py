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
            _dispatch_job(db, job)
            job.status = "dispatched"
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


def _dispatch_job(db: Session, job) -> None:
    """Placeholder dispatch — wire Telnyx outbound call with English script from business_context."""
    logger.info(
        "feedback_ai_followup_call_pending org_id=%s phone=%s context_len=%s",
        job.org_id,
        job.visitor_phone[:6] + "***",
        len(job.business_context or ""),
    )
    # Telnyx voice integration hooks into survey_call_dispatch / voice_agent_runtime in a follow-up pass.
