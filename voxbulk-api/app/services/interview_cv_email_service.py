"""CV intake via careers@ email — per-task toggle and collection window."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

from app.models.service_order import ServiceOrder

CV_EMAIL_ALLOWED_EXTENSIONS = (".pdf", ".docx", ".txt")


def _loads_config(order: ServiceOrder) -> dict[str, Any]:
    try:
        raw = json.loads(order.config_json or "{}")
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def cv_email_settings(order: ServiceOrder) -> dict[str, Any]:
    cfg = _loads_config(order)
    return {
        "enabled": bool(cfg.get("cv_email_enabled")),
        "start_at": cfg.get("cv_email_start_at"),
        "end_at": cfg.get("cv_email_end_at"),
    }


def cv_email_window_state(order: ServiceOrder, *, now: datetime | None = None) -> str:
    """Return: disabled | before | open | after | incomplete"""
    settings = cv_email_settings(order)
    if not settings["enabled"]:
        return "disabled"
    start = _parse_iso(settings.get("start_at"))
    end = _parse_iso(settings.get("end_at"))
    if start is None or end is None:
        return "incomplete"
    ts = now or datetime.utcnow()
    if ts < start:
        return "before"
    if ts > end:
        return "after"
    return "open"


def cv_collection_complete(order: ServiceOrder, *, now: datetime | None = None) -> bool:
    """True when email CV intake is off, the collection window has ended, or closed early."""
    cfg = _loads_config(order)
    if cfg.get("cv_collection_closed_early_at"):
        return True
    state = cv_email_window_state(order, now=now)
    return state in {"disabled", "after"}


def close_cv_collection_early(db: Session, order: ServiceOrder, *, now: datetime | None = None) -> dict[str, Any]:
    """End CV email intake immediately so quote/pay/AI calls can proceed."""
    if order.service_code != "interview":
        raise ValueError("CV collection is only for interview tasks")
    cfg = _loads_config(order)
    if not cfg.get("cv_email_enabled"):
        raise ValueError("CV email collection is not enabled on this task")

    sync_result: dict[str, Any] = {"ok": True, "skipped": True, "message": "Mailbox sync skipped"}
    try:
        from app.services.career_mailbox_sync_service import sync_career_mailbox

        sync_result = sync_career_mailbox(db)
        db.refresh(order)
    except Exception:
        logger.exception("cv_close_early_mailbox_sync_failed order_id=%s", order.id)

    ts = now or datetime.utcnow()
    cfg = _loads_config(order)
    cfg["cv_email_end_at"] = ts.isoformat()
    cfg["cv_collection_closed_early_at"] = ts.isoformat()
    order.config_json = json.dumps(cfg, ensure_ascii=False)
    order.updated_at = ts
    db.add(order)
    db.commit()
    db.refresh(order)
    payload = interview_cv_phase_payload(order, now=ts)
    payload["mailbox_sync"] = {
        "ok": bool(sync_result.get("ok")),
        "processed": int(sync_result.get("processed") or 0),
        "added_cvs": int(sync_result.get("added_cvs") or 0),
        "rejected": int(sync_result.get("rejected") or 0),
        "message": str(sync_result.get("message") or ""),
    }
    return payload


def assert_cv_collection_complete(order: ServiceOrder, *, now: datetime | None = None) -> None:
    if order.service_code != "interview":
        return
    state = cv_email_window_state(order, now=now)
    if state == "disabled":
        return
    if state == "incomplete":
        raise ValueError("CV collection via email is ON — set start and end times before launching AI interviews")
    if state == "before":
        raise ValueError("CV collection has not started yet — AI interviews unlock after the email collection window ends")
    if state == "open":
        end_label = format_cv_email_end_label(order)
        raise ValueError(
            f"CV collection is still open until {end_label}. "
            "Wait for email submissions to finish, then quote and pay based on the final candidate list."
        )


def assert_ai_call_window_after_cv_collection(order: ServiceOrder) -> None:
    if order.service_code != "interview":
        return
    settings = cv_email_settings(order)
    if not settings["enabled"]:
        return
    cv_end = _parse_iso(settings.get("end_at"))
    if cv_end is None or order.scheduled_start_at is None:
        return
    ai_start = order.scheduled_start_at
    if isinstance(ai_start, datetime) and ai_start < cv_end:
        raise ValueError(
            f"AI calling cannot start before CV collection ends ({format_cv_email_end_label(order)}). "
            "Set the AI calling window to start after email intake closes."
        )


def interview_cv_phase_payload(order: ServiceOrder, *, now: datetime | None = None) -> dict[str, Any]:
    state = cv_email_window_state(order, now=now)
    settings = cv_email_settings(order)
    complete = cv_collection_complete(order, now=now)
    cfg = _loads_config(order)
    closed_early = bool(cfg.get("cv_collection_closed_early_at"))
    return {
        "enabled": settings["enabled"],
        "window_state": state,
        "collection_complete": complete,
        "closed_early": closed_early,
        "can_quote": complete,
        "can_launch_ai": complete,
        "start_at": settings.get("start_at"),
        "end_at": settings.get("end_at"),
        "end_label": format_cv_email_end_label(order) if settings.get("end_at") else None,
    }


def format_cv_email_end_label(order: ServiceOrder) -> str:
    settings = cv_email_settings(order)
    end = _parse_iso(settings.get("end_at"))
    if not end:
        return "the scheduled end time"
    return end.strftime("%d %b %Y, %H:%M UTC")
