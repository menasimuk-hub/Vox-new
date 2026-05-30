"""Post-payment interview launch: WhatsApp booking invites + schedule (no immediate dial)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.services.interview_booking_service import InterviewBookingService
from app.services.interview_billing_context import org_interview_billing_context
from app.services.platform_catalog_service import ServiceOrderService


def _order_config(order: ServiceOrder) -> dict[str, Any]:
    try:
        data = json.loads(order.config_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


class InterviewLaunchService:
    @staticmethod
    def approve_for_subscription_package(db: Session, order: ServiceOrder, org: Organisation) -> ServiceOrder:
        """Mark interview order paid under an active monthly package (no per-order checkout)."""
        if order.service_code != "interview":
            raise ValueError("Launch is only for interview orders")
        if order.recipient_count <= 0:
            raise ValueError("Upload candidates before launch")

        ctx = org_interview_billing_context(db, org)
        if not ctx.get("has_active_subscription") or str(ctx.get("billing_mode") or "") != "package":
            raise ValueError("An active monthly package is required to launch without payment")

        if order.payment_status != "approved":
            try:
                order = ServiceOrderService.quote_order(db, order)
            except ValueError:
                db.refresh(order)
            plan_name = str(ctx.get("plan_name") or "package").strip() or "package"
            order.payment_method = "subscription"
            order.payment_status = "approved"
            order.status = "paid"
            order.payment_note = f"Included in {plan_name} subscription"
            order.updated_at = datetime.utcnow()
            db.add(order)
            db.commit()
            db.refresh(order)
        return order

    @staticmethod
    def launch_after_payment(
        db: Session,
        order: ServiceOrder,
        *,
        resend_invites: bool = False,
        channels: list[str] | None = None,
    ) -> dict[str, Any]:
        if order.service_code != "interview":
            raise ValueError("Launch is only for interview orders")
        if order.payment_status != "approved":
            raise ValueError("Payment must be approved before launch")

        config = _order_config(order)
        delivery = str(config.get("delivery") or "ai_call").strip().lower()
        invite_result: dict[str, Any] | None = None

        if delivery == "ai_call":
            if not order.scheduled_start_at or not order.scheduled_end_at:
                raise ValueError("Set the calling window (start and end) before launch")
            already_sent = bool(config.get("booking_invites_sent_at"))
            if resend_invites or not already_sent:
                invite_result = InterviewBookingService.send_invites(
                    db,
                    order,
                    channels=channels or ["whatsapp", "email"],
                )
            config = _order_config(order)
            config["require_booking"] = config.get("require_booking", True) is not False
            config["booking_flow"] = "whatsapp_slot"
            order.config_json = json.dumps(config, ensure_ascii=False)
            db.add(order)
            db.commit()
            db.refresh(order)

        order = ServiceOrderService.schedule_order(db, order)
        return {
            "ok": True,
            "order_id": order.id,
            "status": order.status,
            "invites": invite_result,
            "message": (
                "Booking invites sent. Candidates choose a slot via WhatsApp; "
                "AI calls run at each booked time within your calling window."
            ),
        }
