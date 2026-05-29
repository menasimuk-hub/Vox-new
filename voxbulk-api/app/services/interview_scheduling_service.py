"""Send booking links to shortlisted interview candidates (WhatsApp + email)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder
from app.services.interview_booking_service import InterviewBookingService
from app.services.platform_catalog_service import ServiceOrderService


def _order_config(order: ServiceOrder) -> dict[str, Any]:
    try:
        data = json.loads(order.config_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


class InterviewSchedulingService:
    @staticmethod
    def save_shortlist(db: Session, order: ServiceOrder, recipient_ids: list[str]) -> dict[str, Any]:
        if order.service_code != "interview":
            raise ValueError("Shortlist is only for interview orders")
        ids = [str(x).strip() for x in recipient_ids if str(x).strip()][:10]
        recipients = ServiceOrderService.get_recipients(db, order.id)
        valid = {r.id for r in recipients}
        ids = [rid for rid in ids if rid in valid]
        config = _order_config(order)
        config["top_10_recipient_ids"] = ids
        config["shortlist_saved_at"] = datetime.utcnow().isoformat()
        order.config_json = json.dumps(config, ensure_ascii=False)
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(order)
        return {"ok": True, "recipient_ids": ids, "count": len(ids)}

    @staticmethod
    def send_scheduling_links(
        db: Session,
        order: ServiceOrder,
        *,
        recipient_ids: list[str] | None = None,
        channels: list[str] | None = None,
    ) -> dict[str, Any]:
        if order.service_code != "interview":
            raise ValueError("Scheduling send is only for interview orders")

        config = _order_config(order)
        ids = recipient_ids or list(config.get("top_10_recipient_ids") or [])
        ids = [str(x).strip() for x in ids if str(x).strip()][:10]
        if not ids:
            raise ValueError("Select at least one candidate")

        channel_list = channels
        if channel_list is None:
            channel_list = list(config.get("scheduling_channels") or ["whatsapp", "email"])

        result = InterviewBookingService.send_invites(
            db,
            order,
            recipient_ids=ids,
            channels=channel_list,
        )
        config = _order_config(order)
        config["scheduling_sent_at"] = datetime.utcnow().isoformat()
        order.config_json = json.dumps(config, ensure_ascii=False)
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()

        return {
            "ok": True,
            "sent": int(result.get("whatsapp_sent") or 0) + int(result.get("email_sent") or 0),
            "whatsapp_sent": result.get("whatsapp_sent"),
            "email_sent": result.get("email_sent"),
            "errors": result.get("errors") or [],
        }
