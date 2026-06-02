"""Post-payment interview launch: WhatsApp booking invites + schedule (no immediate dial)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.services.interview_booking_service import InterviewBookingService
from app.services.interview_billing_context import org_interview_billing_context, plan_allows_cv_email
from app.services.gocardless_service import BillingService
from app.services.platform_catalog_service import ServiceOrderService


def _order_config(order: ServiceOrder) -> dict[str, Any]:
    try:
        data = json.loads(order.config_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


class InterviewLaunchService:
    @staticmethod
    def org_has_package_launch_access(db: Session, org: Organisation) -> bool:
        """True when org may launch interviews without per-order checkout."""
        ctx = org_interview_billing_context(db, org)
        if ctx.get("has_active_subscription"):
            return True
        sub = BillingService.get_subscription(db, org.id)
        plan = BillingService.resolve_active_plan(db, org.id)
        status = str(sub.status or "").strip().lower() if sub else ""
        return (
            sub is not None
            and status in {"active", "trial", "past_due"}
            and plan_allows_cv_email(plan)
        )

    @staticmethod
    def approve_for_subscription_package(db: Session, order: ServiceOrder, org: Organisation) -> ServiceOrder:
        """Mark interview order paid under an active monthly package (no per-order checkout)."""
        if order.service_code != "interview":
            raise ValueError("Launch is only for interview orders")
        if order.recipient_count <= 0:
            cfg = _order_config(order)
            if cfg.get("cv_email_enabled"):
                raise ValueError(
                    "No CVs received yet — wait for email submissions to careers@voxbulk.com "
                    "or upload candidates manually"
                )
            raise ValueError("Upload candidates before launch")

        if not InterviewLaunchService.org_has_package_launch_access(db, org):
            raise ValueError("An active monthly package is required to launch without payment")

        ctx = org_interview_billing_context(db, org)
        if order.payment_status != "approved":
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
        from app.services.interview_booking_service import _assert_order_accepts_invite_changes

        _assert_order_accepts_invite_changes(order)
        if order.payment_status != "approved":
            raise ValueError("Payment must be approved before launch")

        config = _order_config(order)
        delivery = str(config.get("delivery") or "ai_call").strip().lower()
        invite_result: dict[str, Any] | None = None

        if delivery == "ai_call":
            if not order.scheduled_start_at or not order.scheduled_end_at:
                raise ValueError("Set the calling window (start and end) before launch")
            dispatch = config.get("last_invite_dispatch")
            dispatch_ok = isinstance(dispatch, dict) and bool(dispatch.get("ok"))
            needs_invites = (
                resend_invites
                or not config.get("booking_invites_sent_at")
                or not dispatch_ok
                or InterviewBookingService.recipients_pending_invite_email(db, order)
            )
            if needs_invites:
                invite_result = InterviewBookingService.send_invites(
                    db,
                    order,
                    channels=list(channels or ["email", "whatsapp"]),
                    force_resend=resend_invites,
                )
            config = _order_config(order)
            config["require_booking"] = config.get("require_booking", True) is not False
            config["booking_flow"] = "whatsapp_slot"
            order.config_json = json.dumps(config, ensure_ascii=False)
            db.add(order)
            db.commit()
            db.refresh(order)

        order = ServiceOrderService.schedule_order(db, order)
        dispatch = invite_result or {}
        return {
            "ok": bool(dispatch.get("ok", invite_result is None or dispatch.get("email_sent", 0) > 0 or dispatch.get("whatsapp_sent", 0) > 0)),
            "order_id": order.id,
            "status": order.status,
            "invites": invite_result,
            "message": InterviewLaunchService._launch_message(invite_result),
        }

    @staticmethod
    def _launch_message(invite_result: dict[str, Any] | None) -> str:
        if not invite_result:
            return (
                "Campaign scheduled. Booking invites were already sent — use Resend if candidates need another notice."
            )
        email_n = int(invite_result.get("email_sent") or 0)
        wa_n = int(invite_result.get("whatsapp_sent") or 0)
        errors = invite_result.get("errors") or []
        if email_n == 0 and wa_n == 0:
            if errors:
                return f"No invites delivered. First error: {errors[0]}"
            return "No booking invites were sent — check candidate email/phone and SMTP/Telnyx settings."
        parts = []
        if email_n:
            parts.append(f"{email_n} email(s)")
        if wa_n:
            parts.append(f"{wa_n} WhatsApp notice(s)")
        msg = f"Booking invites sent: {', '.join(parts)}."
        if errors:
            msg += f" {len(errors)} issue(s) — see invite details."
        return msg
