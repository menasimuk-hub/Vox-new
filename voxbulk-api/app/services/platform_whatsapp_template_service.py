"""Classify synced Telnyx WhatsApp templates for interviews, surveys, and marketing."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService


def template_purpose(name: str | None, category: str | None) -> str:
    n = str(name or "").strip().lower()
    cat = str(category or "").strip().upper()
    if any(x in n for x in ("booking", "schedule", "appointment", "calendly", "cronofy", "interview_book", "interview_confirm")):
        return "booking"
    if any(x in n for x in ("survey", "feedback", "satisfaction")):
        return "survey"
    if cat == "MARKETING" or "marketing" in n or "promo" in n or "offer" in n:
        return "marketing"
    if "interview" in n or "screen" in n or "recruit" in n:
        return "interview"
    return "other"


def enrich_template_row(row: dict[str, Any]) -> dict[str, Any]:
    purpose = template_purpose(row.get("name"), row.get("category"))
    out = dict(row)
    out["purpose"] = purpose
    out["purpose_label"] = purpose.replace("_", " ").title()
    return out


class PlatformWhatsappTemplateService:
    @staticmethod
    def list_for_dashboard(
        db: Session,
        *,
        approved_only: bool = True,
        purpose: str | None = None,
    ) -> dict[str, Any]:
        rows = TelnyxWhatsappTemplateSyncService.list_stored(db, approved_only=approved_only)
        enriched = [enrich_template_row(r) for r in rows]
        if purpose:
            key = str(purpose).strip().lower()
            enriched = [r for r in enriched if r.get("purpose") == key]
        grouped: dict[str, list[dict[str, Any]]] = {
            "booking": [],
            "survey": [],
            "marketing": [],
            "interview": [],
            "other": [],
        }
        for row in enriched:
            grouped.setdefault(str(row.get("purpose") or "other"), []).append(row)
        return {
            "templates": enriched,
            "grouped": grouped,
            "counts": {k: len(v) for k, v in grouped.items()},
        }
