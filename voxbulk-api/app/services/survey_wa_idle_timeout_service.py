"""Scheduler handlers for WhatsApp survey idle timeouts and abandoned button steps."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.survey_wa_flow_constants import (
    BUTTON_ABANDON_HOURS,
    KEY_SURVEY_STARTED_AT,
    KEY_TUM_DEADLINE,
    KEY_TUM_PENDING,
    LOG_TELL_US_MORE,
)

logger = logging.getLogger(__name__)


def _parse_iso(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def _order_config(order: ServiceOrder) -> dict:
    try:
        cfg = json.loads(order.config_json or "{}")
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def process_tell_us_more_timeouts(db: Session, *, limit: int = 50) -> int:
    """Advance past unanswered low-rating tell-us-more prompts after OPEN_TEXT_TIMEOUT_SEC."""
    from app.services.survey_whatsapp_conversation_service import advance_after_tell_us_more_timeout

    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(ServiceOrderRecipient)
        .where(ServiceOrderRecipient.status == "in_progress")
        .order_by(ServiceOrderRecipient.created_at.asc())
        .limit(max(limit * 10, 50))
    ).scalars().all()

    advanced = 0
    for recipient in rows:
        if advanced >= limit:
            break
        try:
            payload = json.loads(recipient.result_json or "{}")
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        conv = payload.get("wa_conversation") or {}
        if not isinstance(conv, dict) or not conv.get(KEY_TUM_PENDING):
            continue
        deadline = _parse_iso(conv.get(KEY_TUM_DEADLINE))
        if deadline is None or deadline > now:
            continue
        order = db.get(ServiceOrder, recipient.order_id)
        if order is None:
            continue
        config = _order_config(order)
        logger.info(
            "%s tell_us_more_timeout order=%s recipient=%s",
            LOG_TELL_US_MORE,
            order.id,
            recipient.id,
        )
        if advance_after_tell_us_more_timeout(
            db,
            order=order,
            recipient=recipient,
            config=config,
            payload=payload,
            conv=conv,
        ):
            advanced += 1
    return advanced


def process_button_step_abandons(db: Session, *, limit: int = 50) -> int:
    """Mark recipients failed when stuck on a button step with no reply for BUTTON_ABANDON_HOURS."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=BUTTON_ABANDON_HOURS)
    rows = db.execute(
        select(ServiceOrderRecipient)
        .where(ServiceOrderRecipient.status == "in_progress")
        .order_by(ServiceOrderRecipient.created_at.asc())
        .limit(max(limit * 10, 50))
    ).scalars().all()

    abandoned = 0
    for recipient in rows:
        if abandoned >= limit:
            break
        try:
            payload = json.loads(recipient.result_json or "{}")
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        conv = payload.get("wa_conversation") or {}
        if not isinstance(conv, dict):
            continue
        if conv.get(KEY_TUM_PENDING) or conv.get("awaiting_final_feedback_text"):
            continue
        started = _parse_iso(conv.get(KEY_SURVEY_STARTED_AT) or conv.get("started_at"))
        if started is None or started > cutoff:
            continue
        order = db.get(ServiceOrder, recipient.order_id)
        if order is None:
            continue
        config = _order_config(order)
        if str(config.get("channel") or "").lower() not in {"", "whatsapp", "wa"} and not config.get("wa_template_id"):
            from app.services.survey_dispatch_service import _uses_whatsapp

            if not _uses_whatsapp(config):
                continue
        conv["abandon_reason"] = "no_reply_on_button_step_20h"
        payload["wa_conversation"] = conv
        payload["error"] = "Survey incomplete — no reply within 20 hours"
        recipient.status = "failed"
        recipient.result_json = json.dumps(payload, ensure_ascii=False)
        db.add(recipient)
        db.commit()
        logger.info(
            "%s button_step_abandoned order=%s recipient=%s",
            LOG_TELL_US_MORE,
            recipient.order_id,
            recipient.id,
        )
        abandoned += 1
    return abandoned


def process_wa_survey_idle_timeouts(db: Session, *, limit: int = 50) -> int:
    """Run tell-us-more skip, closing skip, and button-step abandon checks."""
    from app.services.survey_wa_final_feedback_service import process_final_feedback_timeouts

    total = 0
    total += process_tell_us_more_timeouts(db, limit=limit)
    total += process_final_feedback_timeouts(db, limit=limit)
    total += process_button_step_abandons(db, limit=limit)
    return total
