"""CV intake via careers@ email — per-task toggle and collection window."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

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
    """Return: disabled | before | open | after"""
    settings = cv_email_settings(order)
    if not settings["enabled"]:
        return "disabled"
    start = _parse_iso(settings.get("start_at"))
    end = _parse_iso(settings.get("end_at"))
    if start is None or end is None:
        return "disabled"
    ts = now or datetime.utcnow()
    if ts < start:
        return "before"
    if ts > end:
        return "after"
    return "open"


def format_cv_email_end_label(order: ServiceOrder) -> str:
    settings = cv_email_settings(order)
    end = _parse_iso(settings.get("end_at"))
    if not end:
        return "the scheduled end time"
    return end.strftime("%d %b %Y, %H:%M UTC")
