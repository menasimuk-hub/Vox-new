"""Customer Feedback billing — GoCardless-only subscription."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.billing_invoice import BillingInvoice
from app.models.customer_feedback import FEEDBACK_SERVICE_CODE, FeedbackPackage, FeedbackUsagePeriod
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.billing_access_service import BillingAccessService
from app.services.billing_currency import resolve_org_currency
from app.services.customer_feedback.catalog_service import FeedbackCatalogService, package_to_dict
from app.services.gocardless_service import BillingService, GoCardlessConfigError, GoCardlessProviderError


class FeedbackBillingError(ValueError):
    pass


class FeedbackBillingService:
    @staticmethod
    def get_active_subscription(db: Session, org_id: str) -> Subscription | None:
        sub = BillingAccessService.get_feedback_subscription(db, org_id)
        if sub is None:
            return None
        if str(sub.status or "").lower() in {"cancelled", "inactive"}:
            return None
        return sub

    @staticmethod
    def get_package_for_plan(db: Session, plan_id: str) -> FeedbackPackage | None:
        return db.execute(select(FeedbackPackage).where(FeedbackPackage.plan_id == plan_id)).scalar_one_or_none()

    @staticmethod
    def _validate_feedback_plan(db: Session, plan: Plan) -> FeedbackPackage:
        if str(plan.service_kind or "") != FEEDBACK_SERVICE_CODE:
            raise FeedbackBillingError("Plan is not a Customer feedback package")
        pkg = FeedbackBillingService.get_package_for_plan(db, plan.id)
        if pkg is None or not pkg.is_active:
            raise FeedbackBillingError("Customer feedback package is not available")
        return pkg

    @staticmethod
    def list_customer_packages(db: Session, org: Organisation) -> list[dict[str, Any]]:
        zone = FeedbackCatalogService.resolve_market_zone(db, org)
        return FeedbackCatalogService.list_packages(db, market_zone=zone, active_only=True)

    @staticmethod
    def subscription_payload(db: Session, org_id: str) -> dict[str, Any]:
        sub = FeedbackBillingService.get_active_subscription(db, org_id)
        if sub is None:
            return {"active": False, "status": "none"}
        plan = db.get(Plan, sub.plan_id)
        pkg = FeedbackBillingService.get_package_for_plan(db, sub.plan_id) if plan else None
        usage = FeedbackBillingService.get_current_usage(db, org_id)
        return {
            "active": str(sub.status or "").lower() in {"active", "pending_first_payment", "trial"},
            "status": sub.status,
            "plan_id": sub.plan_id,
            "plan_name": plan.name if plan else None,
            "service_code": FEEDBACK_SERVICE_CODE,
            "max_locations": pkg.max_locations if pkg else 0,
            "wa_units_included": usage.get("wa_units_included", 0),
            "wa_units_used": usage.get("wa_units_used", 0),
            "wa_units_remaining": usage.get("wa_units_remaining", 0),
            "payment_provider": sub.payment_provider,
            "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
        }

    @staticmethod
    def get_current_usage(db: Session, org_id: str) -> dict[str, Any]:
        row = (
            db.execute(
                select(FeedbackUsagePeriod)
                .where(FeedbackUsagePeriod.org_id == org_id)
                .order_by(FeedbackUsagePeriod.period_start.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if row is None:
            return {"wa_units_included": 0, "wa_units_used": 0, "wa_units_remaining": 0}
        included = int(row.wa_units_included or 0)
        used = int(row.wa_units_used or 0)
        return {
            "wa_units_included": included,
            "wa_units_used": used,
            "wa_units_remaining": max(0, included - used),
        }

    @staticmethod
    def open_usage_period(db: Session, *, org_id: str, subscription: Subscription, pkg: FeedbackPackage) -> FeedbackUsagePeriod:
        now = datetime.utcnow()
        row = FeedbackUsagePeriod(
            id=str(uuid.uuid4()),
            org_id=org_id,
            subscription_id=subscription.id,
            period_start=now,
            period_end=subscription.current_period_end,
            wa_units_included=int(pkg.wa_units_included or 0),
            wa_units_used=0,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def on_subscription_activated(db: Session, *, org_id: str, subscription: Subscription, plan: Plan) -> None:
        subscription.service_code = FEEDBACK_SERVICE_CODE
        pkg = FeedbackBillingService._validate_feedback_plan(db, plan)
        existing = (
            db.execute(
                select(FeedbackUsagePeriod)
                .where(FeedbackUsagePeriod.subscription_id == subscription.id)
                .limit(1)
            )
            .scalars()
            .first()
        )
        if existing:
            return
        FeedbackBillingService.open_usage_period(db, org_id=org_id, subscription=subscription, pkg=pkg)

    @staticmethod
    def start_gocardless_signup(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        plan_id: str,
    ) -> dict[str, Any]:
        plan = db.get(Plan, plan_id)
        if plan is None:
            raise FeedbackBillingError("Unknown plan")
        FeedbackBillingService._validate_feedback_plan(db, plan)
        existing = FeedbackBillingService.get_active_subscription(db, org_id)
        if existing and str(existing.status or "").lower() == "active":
            raise FeedbackBillingError("An active Customer feedback subscription already exists. Upgrade from Account → Customer feedback packages.")
        try:
            res = BillingService.start_gocardless_redirect_flow(
                db,
                org_id=org_id,
                user_id=user_id,
                plan_id=plan.id,
            )
        except (GoCardlessConfigError, GoCardlessProviderError, ValueError) as exc:
            raise FeedbackBillingError(str(exc)) from exc
        from app.models.billing_redirect_flow import BillingRedirectFlow

        flow = db.execute(
            select(BillingRedirectFlow).where(BillingRedirectFlow.redirect_flow_id == res["redirect_flow_id"])
        ).scalar_one_or_none()
        if flow is not None:
            flow.flow_purpose = FEEDBACK_SERVICE_CODE
            db.add(flow)
            db.commit()
        return res

    @staticmethod
    def complete_gocardless_signup(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        redirect_flow_id: str,
    ) -> dict[str, Any]:
        try:
            res = BillingService.complete_gocardless_redirect_flow(
                db,
                org_id=org_id,
                user_id=user_id,
                redirect_flow_id=redirect_flow_id,
            )
        except (GoCardlessConfigError, GoCardlessProviderError, ValueError) as exc:
            raise FeedbackBillingError(str(exc)) from exc
        sub = res.get("subscription")
        plan = res.get("plan")
        if sub is not None and plan is not None:
            FeedbackBillingService._tag_activation_invoice(db, org_id=org_id)
        return res

    @staticmethod
    def _tag_activation_invoice(db: Session, *, org_id: str) -> None:
        row = (
            db.execute(
                select(BillingInvoice)
                .where(BillingInvoice.org_id == org_id, BillingInvoice.kind == "subscription")
                .order_by(BillingInvoice.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if row is None:
            return
        row.service_code = FEEDBACK_SERVICE_CODE
        if row.invoice_number and not str(row.invoice_number).startswith("CF-"):
            row.invoice_number = f"CF-{row.invoice_number}"
        db.add(row)
        db.commit()

    @staticmethod
    def ensure_units_available(db: Session, org_id: str) -> tuple[bool, str | None]:
        sub = FeedbackBillingService.get_active_subscription(db, org_id)
        if sub is None:
            return False, "Subscribe to a Customer feedback package to start collecting responses."
        usage = FeedbackBillingService.get_current_usage(db, org_id)
        if int(usage.get("wa_units_remaining") or 0) <= 0:
            return False, "Your included WhatsApp survey units are used up. Upgrade your Customer feedback package to continue."
        return True, None

    @staticmethod
    def consume_unit(db: Session, org_id: str) -> None:
        row = (
            db.execute(
                select(FeedbackUsagePeriod)
                .where(FeedbackUsagePeriod.org_id == org_id)
                .order_by(FeedbackUsagePeriod.period_start.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if row is None:
            raise FeedbackBillingError("No active usage period")
        if int(row.wa_units_used or 0) >= int(row.wa_units_included or 0):
            raise FeedbackBillingError("No WhatsApp units remaining")
        row.wa_units_used = int(row.wa_units_used or 0) + 1
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()

    @staticmethod
    def max_locations(db: Session, org_id: str) -> int:
        sub = FeedbackBillingService.get_active_subscription(db, org_id)
        if sub is None:
            return 0
        pkg = FeedbackBillingService.get_package_for_plan(db, sub.plan_id)
        return int(pkg.max_locations or 0) if pkg else 0
