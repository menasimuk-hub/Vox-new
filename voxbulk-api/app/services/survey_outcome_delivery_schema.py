"""Normalized outcome_delivery_json shape for WA Survey sessions (P6)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any


def loads_outcome_delivery(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return normalize_outcome_delivery(data if isinstance(data, dict) else {})
    except Exception:
        return {}


def normalize_outcome_delivery(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure a consistent delivery record for admin/ops and idempotency checks."""
    sent_at = data.get("sent_at")
    ok = bool(data.get("ok")) if "ok" in data else bool(data.get("sent"))
    return {
        "sent_at": str(sent_at) if sent_at else None,
        "ok": ok,
        "sent": bool(data.get("sent", ok)),
        "skipped": bool(data.get("skipped")),
        "channel": str(data.get("channel") or "whatsapp"),
        "action_type": str(data.get("action_type") or ""),
        "used_text_fallback": bool(data.get("used_text_fallback")),
        "template_send_failed": bool(data.get("template_send_failed")),
        "outcome_key": str(data.get("outcome_key") or ""),
        "template_id": data.get("template_id"),
        "detail": str(data.get("detail") or "")[:500],
        "external_id": str(data["external_id"]) if data.get("external_id") else None,
        "body_preview": str(data.get("body_preview") or "")[:200],
        "provider_status": str(data.get("provider_status") or "") or None,
    }


def build_outcome_delivery_record(
    *,
    ok: bool,
    channel: str,
    action_type: str,
    used_text_fallback: bool,
    outcome_key: str,
    template_id: Any,
    detail: str,
    external_id: str | None,
    body_preview: str,
    template_send_failed: bool = False,
    skipped: bool = False,
    provider_status: str | None = None,
    sent_at: str | None = None,
) -> dict[str, Any]:
    now = sent_at or datetime.utcnow().isoformat()
    return normalize_outcome_delivery(
        {
            "sent_at": now,
            "ok": ok,
            "sent": ok and not skipped,
            "skipped": skipped,
            "channel": channel,
            "action_type": action_type,
            "used_text_fallback": used_text_fallback,
            "template_send_failed": template_send_failed,
            "outcome_key": outcome_key,
            "template_id": template_id,
            "detail": detail,
            "external_id": external_id,
            "body_preview": body_preview,
            "provider_status": provider_status,
        }
    )


def dumps_outcome_delivery(record: dict[str, Any]) -> str:
    return json.dumps(normalize_outcome_delivery(record), ensure_ascii=False)
