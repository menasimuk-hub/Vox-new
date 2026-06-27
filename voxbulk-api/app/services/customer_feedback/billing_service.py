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
from app.services.plan_price_service import PlanPriceService
from app.services.subscription_cancellation_service import (
    SubscriptionCancellationError,
    SubscriptionCancellationService,
)


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
            return {"active": False, "status": "none", "finance": None}
        plan = db.get(Plan, sub.plan_id)
        pkg = FeedbackBillingService.get_package_for_plan(db, sub.plan_id) if plan else None
        usage = FeedbackBillingService.get_current_usage(db, org_id)
        from app.services.subscription_summary_service import SubscriptionSummaryService

        finance = SubscriptionSummaryService.feedback_summary(db, org_id)
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
            "web_units_included": usage.get("web_units_included", 0),
            "web_units_used": usage.get("web_units_used", 0),
            "web_units_remaining": usage.get("web_units_remaining", 0),
            "payment_provider": sub.payment_provider,
            "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
            "finance": finance,
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
            return {
                "wa_units_included": 0,
                "wa_units_used": 0,
                "wa_units_remaining": 0,
                "web_units_included": 0,
                "web_units_used": 0,
                "web_units_remaining": 0,
            }
        wa_included = int(row.wa_units_included or 0)
        wa_used = int(row.wa_units_used or 0)
        web_included = int(row.web_units_included or 0)
        web_used = int(row.web_units_used or 0)
        web_remaining = 999_999 if web_included < 0 else max(0, web_included - web_used)
        return {
            "wa_units_included": wa_included,
            "wa_units_used": wa_used,
            "wa_units_remaining": max(0, wa_included - wa_used),
            "web_units_included": web_included,
            "web_units_used": web_used,
            "web_units_remaining": web_remaining,
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
            web_units_included=int(pkg.web_units_included or 0),
            web_units_used=0,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def _enable_feedback_module(db: Session, org_id: str, *, commit: bool = True) -> None:
        org = db.get(Organisation, org_id)
        if org is None:
            return
        from app.services.org_enabled_services import (
            parse_enabled_services,
            serialize_enabled_services,
        )

        allowed = parse_enabled_services(getattr(org, "allowed_services_json", None))
        enabled = parse_enabled_services(getattr(org, "enabled_services_json", None))
        allowed["customer_feedback"] = True
        enabled["customer_feedback"] = True
        org.allowed_services_json = serialize_enabled_services(allowed)
        org.enabled_services_json = serialize_enabled_services(enabled)
        org.updated_at = datetime.utcnow()
        db.add(org)
        if commit:
            db.commit()

    @staticmethod
    def on_subscription_activated(db: Session, *, org_id: str, subscription: Subscription, plan: Plan) -> None:
        subscription.service_code = FEEDBACK_SERVICE_CODE
        db.add(subscription)
        pkg = FeedbackBillingService._validate_feedback_plan(db, plan)
        FeedbackBillingService._enable_feedback_module(db, org_id, commit=False)
        existing = (
            db.execute(
                select(FeedbackUsagePeriod)
                .where(FeedbackUsagePeriod.subscription_id == subscription.id)
                .limit(1)
            )
            .scalars()
            .first()
        )
        if existing is None:
            now = datetime.utcnow()
            row = FeedbackUsagePeriod(
                id=str(uuid.uuid4()),
                org_id=org_id,
                subscription_id=subscription.id,
                period_start=now,
                period_end=subscription.current_period_end,
                wa_units_included=int(pkg.wa_units_included or 0),
                wa_units_used=0,
                web_units_included=int(pkg.web_units_included or 0),
                web_units_used=0,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
        db.commit()

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
                flow_purpose=FEEDBACK_SERVICE_CODE,
            )
        except (GoCardlessConfigError, GoCardlessProviderError, ValueError) as exc:
            raise FeedbackBillingError(str(exc)) from exc
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
    def ensure_web_units_available(db: Session, org_id: str) -> tuple[bool, str | None]:
        sub = FeedbackBillingService.get_active_subscription(db, org_id)
        if sub is None:
            return False, "Subscribe to a Customer feedback package to run web surveys."
        usage = FeedbackBillingService.get_current_usage(db, org_id)
        web_included = int(usage.get("web_units_included") or 0)
        if web_included < 0:
            return True, None
        if int(usage.get("web_units_remaining") or 0) <= 0:
            return False, "Your included web survey units are used up. Upgrade your Customer feedback package to continue."
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
    def consume_web_unit(db: Session, org_id: str) -> None:
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
        web_included = int(row.web_units_included or 0)
        if web_included >= 0 and int(row.web_units_used or 0) >= web_included:
            raise FeedbackBillingError("No web survey units remaining")
        if web_included >= 0:
            row.web_units_used = int(row.web_units_used or 0) + 1
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

    @staticmethod
    def on_period_renewed(db: Session, *, org_id: str, subscription: Subscription, plan: Plan) -> None:
        pkg = FeedbackBillingService.get_package_for_plan(db, plan.id)
        if pkg is None:
            return
        FeedbackBillingService.open_usage_period(db, org_id=org_id, subscription=subscription, pkg=pkg)

    @staticmethod
    def change_plan(
        db: Session,
        *,
        org_id: str,
        plan_id: str,
    ) -> dict[str, Any]:
        sub = BillingAccessService.get_feedback_subscription(db, org_id)
        if sub is None or str(sub.status or "").lower() not in {"active", "trial", "pending_first_payment"}:
            raise FeedbackBillingError("No active Customer feedback subscription")
        new_plan = db.get(Plan, plan_id)
        if new_plan is None:
            raise FeedbackBillingError("Unknown plan")
        new_pkg = FeedbackBillingService._validate_feedback_plan(db, new_plan)
        old_plan = db.get(Plan, sub.plan_id)
        if old_plan is None:
            raise FeedbackBillingError("Current plan not found")
        if new_plan.id == old_plan.id:
            return {"ok": True, "direction": "same", "plan_id": new_plan.id}

        org = db.get(Organisation, org_id)
        if org is None:
            raise FeedbackBillingError("Organisation not found")

        _currency, old_monthly = PlanPriceService.monthly_minor_for_org(db, org, old_plan)
        _currency, new_monthly = PlanPriceService.monthly_minor_for_org(db, org, new_plan)
        if new_monthly > old_monthly:
            from app.services.billing_lifecycle_service import BillingLifecycleService
            from app.services.invoice_service import InvoiceService
            from app.services.usage_wallet_service import UsageWalletService

            pro_rata = BillingLifecycleService.calculate_pro_rata_minor(
                db, org=org, sub=sub, old_plan=old_plan, new_plan=new_plan
            )
            invoice_id = None
            if pro_rata > 0 and str(sub.payment_provider or "").lower() == "gocardless":
                currency = PlanPriceService.monthly_minor_for_org(db, org, new_plan)[0]
                email = UsageWalletService.get_org_billing_email(db, org_id) or (org.contact_email or "")
                desc = f"Pro-rata upgrade to {new_plan.name}"
                external_id = f"cf-pro-rata:{sub.id}:{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
                invoice = InvoiceService.create_from_payment(
                    db,
                    org_id=org_id,
                    client_email=email,
                    subtotal_pence=pro_rata,
                    currency=currency,
                    description=desc,
                    provider="gocardless",
                    external_invoice_id=external_id,
                    payment_method="gocardless",
                    status="pending",
                    line_items=[
                        {
                            "description": desc,
                            "quantity": 1,
                            "unit_pence": pro_rata,
                            "total_pence": pro_rata,
                        }
                    ],
                    kind="pro_rata",
                )
                invoice.service_code = FEEDBACK_SERVICE_CODE
                db.add(invoice)
                db.commit()
                invoice_id = invoice.id
                try:
                    payment = BillingService.collect_mandate_payment(
                        db,
                        org_id=org_id,
                        amount_pence=pro_rata,
                        description=desc,
                        currency=currency,
                        metadata={"invoice_id": invoice.id, "service_code": FEEDBACK_SERVICE_CODE},
                    )
                    if payment is not None:
                        invoice.dd_payment_id = str(payment.get("payment_id") or "")
                        invoice.dd_status = str(payment.get("status") or "pending_submission")
                        invoice.payment_reference = invoice.dd_payment_id
                        invoice.status = "collecting"
                        db.add(invoice)
                        db.commit()
                except (GoCardlessConfigError, GoCardlessProviderError):
                    invoice.dd_status = "submission_failed"
                    db.add(invoice)
                    db.commit()

                from app.services.billing_event_email_service import BillingEventEmailService

                try:
                    db.refresh(invoice)
                    BillingEventEmailService.issue_payment_invoice(db, invoice=invoice)
                except Exception:
                    pass

            sub.plan_id = new_plan.id
            sub.pending_plan_id = None
            sub.updated_at = datetime.utcnow()
            db.add(sub)
            db.commit()

            old_pkg = FeedbackBillingService.get_package_for_plan(db, old_plan.id)
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
            if row is not None and old_pkg is not None:
                wa_delta = int(new_pkg.wa_units_included or 0) - int(old_pkg.wa_units_included or 0)
                web_delta = int(new_pkg.web_units_included or 0) - int(old_pkg.web_units_included or 0)
                changed = False
                if wa_delta > 0:
                    row.wa_units_included = int(row.wa_units_included or 0) + wa_delta
                    changed = True
                if web_delta > 0:
                    row.web_units_included = int(row.web_units_included or 0) + web_delta
                    changed = True
                if changed:
                    row.updated_at = datetime.utcnow()
                    db.add(row)
                    db.commit()
            return {
                "ok": True,
                "direction": "upgrade",
                "plan_id": new_plan.id,
                "pro_rata_minor": pro_rata,
                "invoice_id": invoice_id,
            }

        if new_monthly < old_monthly:
            sub.pending_plan_id = new_plan.id
            sub.updated_at = datetime.utcnow()
            db.add(sub)
            db.commit()
            return {"ok": True, "direction": "downgrade", "pending_plan_id": new_plan.id}

        sub.plan_id = new_plan.id
        sub.pending_plan_id = None
        sub.updated_at = datetime.utcnow()
        db.add(sub)
        db.commit()
        return {"ok": True, "direction": "same", "plan_id": new_plan.id}

    @staticmethod
    def admin_assign_plan(
        db: Session,
        *,
        org_id: str,
        plan_id: str | None = None,
        plan_code: str | None = None,
        status: str = "active",
    ) -> tuple[Subscription, Plan, str]:
        plan = None
        if plan_id:
            plan = db.get(Plan, plan_id)
        if plan is None and plan_code:
            plan = db.execute(select(Plan).where(Plan.code == str(plan_code).strip().lower())).scalar_one_or_none()
        if plan is None:
            raise FeedbackBillingError("Unknown plan")
        FeedbackBillingService._validate_feedback_plan(db, plan)

        status_val = str(status or "active").strip().lower() or "active"
        existing = BillingAccessService.get_feedback_subscription(db, org_id)
        if existing is not None and str(existing.status or "").lower() in {"active", "trial", "pending_first_payment"}:
            if existing.plan_id == plan.id and str(existing.status or "").lower() == status_val:
                return existing, plan, "same"
            FeedbackBillingService.change_plan(db, org_id=org_id, plan_id=plan.id)
            db.refresh(existing)
            if status_val and str(existing.status or "").lower() != status_val:
                existing.status = status_val
                existing.updated_at = datetime.utcnow()
                db.add(existing)
                db.commit()
                db.refresh(existing)
            return existing, plan, "change"

        now = datetime.utcnow()
        period_end = now + timedelta(days=30)
        if existing is not None:
            sub = existing
            sub.plan_id = plan.id
            sub.service_code = FEEDBACK_SERVICE_CODE
            sub.status = status_val
            sub.pending_plan_id = None
            sub.current_period_end = period_end
            sub.payment_provider = "manual_cash"
            sub.payment_mode = "test"
            sub.updated_at = now
            db.add(sub)
            db.commit()
            db.refresh(sub)
            FeedbackBillingService.on_subscription_activated(db, org_id=org_id, subscription=sub, plan=plan)
            return sub, plan, "reactivate"

        sub = Subscription(
            org_id=org_id,
            plan_id=plan.id,
            service_code=FEEDBACK_SERVICE_CODE,
            status=status_val,
            current_period_end=period_end,
            payment_provider="manual_cash",
            payment_mode="test",
            updated_at=now,
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
        FeedbackBillingService.on_subscription_activated(db, org_id=org_id, subscription=sub, plan=plan)
        return sub, plan, "create"

    @staticmethod
    def cancellation_payload(db: Session, org_id: str) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        if org is None:
            raise FeedbackBillingError("Organisation not found")
        sub = BillingAccessService.get_feedback_subscription(db, org_id)
        plan = db.get(Plan, sub.plan_id) if sub else None
        refund_review = SubscriptionCancellationService.get_open_refund_review(db, org_id) if sub else None
        return SubscriptionCancellationService.cancellation_dict(db, org, sub, plan, refund_review=refund_review)

    @staticmethod
    def request_cancellation(
        db: Session,
        *,
        org_id: str,
        user_id: str | None,
        reason: str | None = None,
        requested_refund_type: str = "none",
    ) -> dict[str, Any]:
        try:
            return SubscriptionCancellationService.request_cancellation(
                db,
                org_id=org_id,
                user_id=user_id,
                reason=reason,
                requested_refund_type=requested_refund_type,
                service_code=FEEDBACK_SERVICE_CODE,
            )
        except SubscriptionCancellationError as exc:
            raise FeedbackBillingError(str(exc)) from exc

    @staticmethod
    def reverse_cancellation(
        db: Session,
        *,
        org_id: str,
        user_id: str | None,
        note: str | None = None,
    ) -> dict[str, Any]:
        try:
            return SubscriptionCancellationService.reverse_cancellation(
                db,
                org_id=org_id,
                admin_user_id=user_id,
                note=note or "Customer reversed scheduled cancellation",
                service_code=FEEDBACK_SERVICE_CODE,
            )
        except SubscriptionCancellationError as exc:
            raise FeedbackBillingError(str(exc)) from exc
