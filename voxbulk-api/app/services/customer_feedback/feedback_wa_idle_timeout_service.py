"""Idle timeouts for Customer Feedback WhatsApp tell-us-more prompts."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackSession
from app.services.customer_feedback.feedback_wa_session_state import (
    is_tell_us_more_pending,
    load_feedback_session_state,
    parse_deadline,
    save_feedback_session_state,
)
from app.services.customer_feedback.whatsapp_service import FeedbackWhatsappService

logger = logging.getLogger(__name__)


def process_feedback_tell_us_more_timeouts(db: Session, *, limit: int = 50) -> int:
    """Skip unanswered tell-us-more after OPEN_TEXT_TIMEOUT_SEC and send next step."""
    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(FeedbackSession)
        .where(FeedbackSession.status == "active")
        .where(FeedbackSession.visitor_phone.notlike("web:%"))
        .order_by(FeedbackSession.started_at.asc())
        .limit(max(limit * 10, 50))
    ).scalars().all()

    advanced = 0
    for session in rows:
        if advanced >= limit:
            break
        state = load_feedback_session_state(session)
        if not is_tell_us_more_pending(state):
            continue
        deadline = parse_deadline(state)
        if deadline is None or deadline > now:
            continue
        step_index = int(state.get("tell_us_more_step_index") or session.current_step or 0)
        session.current_step = step_index + 1
        save_feedback_session_state(session, {})
        db.add(session)
        db.commit()
        logger.info(
            "feedback_wa_tell_us_more_timeout session_id=%s step=%s",
            session.id,
            step_index,
        )
        FeedbackWhatsappService._continue_after_step(db, session=session)
        advanced += 1
    return advanced


def process_feedback_web_tell_us_more_timeouts(db: Session, *, limit: int = 50) -> int:
    """Auto-advance web sessions past expired tell-us-more without a reply."""
    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(FeedbackSession)
        .where(FeedbackSession.status == "active")
        .where(FeedbackSession.visitor_phone.like("web:%"))
        .order_by(FeedbackSession.started_at.asc())
        .limit(max(limit * 10, 50))
    ).scalars().all()

    advanced = 0
    for session in rows:
        if advanced >= limit:
            break
        state = load_feedback_session_state(session)
        if not is_tell_us_more_pending(state):
            continue
        deadline = parse_deadline(state)
        if deadline is None or deadline > now:
            continue
        step_index = int(state.get("tell_us_more_step_index") or session.current_step or 0)
        session.current_step = step_index + 1
        save_feedback_session_state(session, {})
        db.add(session)
        db.commit()
        advanced += 1
    return advanced


def process_feedback_wa_idle_timeouts(db: Session, *, limit: int = 50) -> int:
    total = 0
    total += process_feedback_tell_us_more_timeouts(db, limit=limit)
    total += process_feedback_web_tell_us_more_timeouts(db, limit=limit)
    return total
