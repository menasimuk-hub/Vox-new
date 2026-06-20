"""Shared survey result formatting for CRM write-back."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.models.service_order import ServiceOrder, ServiceOrderRecipient


def parse_recipient_result(recipient: ServiceOrderRecipient) -> dict[str, Any]:
    try:
        result = json.loads(recipient.result_json or "{}")
    except Exception:
        result = {}
    return result if isinstance(result, dict) else {}


def survey_result_fields(order: ServiceOrder, recipient: ServiceOrderRecipient) -> dict[str, Any]:
    result = parse_recipient_result(recipient)
    analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
    sentiment = str(analysis.get("sentiment") or result.get("sentiment") or "").strip()
    score = analysis.get("recommend_score", result.get("recommend_score"))
    summary = str(analysis.get("short_summary") or result.get("short_summary") or "").strip()
    completed_raw = getattr(recipient, "completed_at", None) or result.get("completed_at")
    if hasattr(completed_raw, "isoformat"):
        completed_at = completed_raw.isoformat()
    elif completed_raw:
        completed_at = str(completed_raw)
    else:
        completed_at = datetime.utcnow().isoformat() + "Z"
    return {
        "sentiment": sentiment,
        "score": score,
        "summary": summary,
        "completed_at": completed_at,
        "campaign": str(order.title or "Survey").strip(),
    }


def survey_result_summary(order: ServiceOrder, recipient: ServiceOrderRecipient) -> str:
    fields = survey_result_fields(order, recipient)
    lines = [
        "VoxBulk survey completed",
        f"Campaign: {fields['campaign']}",
    ]
    if fields["sentiment"]:
        lines.append(f"Sentiment: {fields['sentiment']}")
    if fields["score"] is not None:
        lines.append(f"Score: {fields['score']}")
    if fields["summary"]:
        lines.append(f"Summary: {fields['summary'][:500]}")
    lines.append(f"Completed: {fields['completed_at']}")
    return "\n".join(lines)
