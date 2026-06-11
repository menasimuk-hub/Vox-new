"""Unified billing monitor — commercial truth, capacity estimates (display-only), and next actions."""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.billing_invoice import BillingInvoice
from app.models.org_usage_period import OrgUsagePeriod
from app.models.organisation import Organisation
from app.services.billing_access_service import BillingAccessService, OUTSTANDING_STATUSES
from app.services.billing_currency import money_display, resolve_org_currency
from app.services.gocardless_service import BillingService
from app.services.org_service_credit_service import OrgServiceCreditService
from app.services.package_entitlement_service import PackageEntitlementService
from app.services.plan_price_service import PlanPriceService
from app.services.usage_wallet_service import UsageWalletService

ESTIMATE_DISCLAIMER = "Approximate capacity only — not used for billing"


class BillingMonitorService:
    @staticmethod
    def _open_invoices_count(db: Session, org_id: str) -> int:
        return int(
            db.scalar(
                select(func.count())
                .select_from(BillingInvoice)
                .where(
                    BillingInvoice.org_id == org_id,
                    BillingInvoice.status.in_(tuple(OUTSTANDING_STATUSES)),
                )
            )
            or 0
        )

    @staticmethod
    def _wallet_capacity_estimates(
        wallet_pence: int,
        *,
        wa_unit_minor: int,
        per_min_minor: int,
    ) -> tuple[int, int]:
        credit = max(0, int(wallet_pence or 0))
        wa_unit = max(1, int(wa_unit_minor or 0))
        per_min = max(1, int(per_min_minor or 0))
        estimated_wa = credit // wa_unit
        estimated_ai = credit // per_min
        return int(estimated_wa), int(estimated_ai)

    @staticmethod
    def _resolve_next_action(
        *,
        package_remaining_pence: int,
        wallet_pence: int,
        has_subscription: bool,
        pending_overage_pence: int,
        can_launch: bool,
        launch_block_reason: str | None,
    ) -> tuple[str, str]:
        if launch_block_reason:
            if "credit limit" in launch_block_reason.lower() or "past-due" in launch_block_reason.lower():
                return "contact_support", "Resolve open invoices before launching"
            return "contact_support", launch_block_reason

        if package_remaining_pence > 0:
            return "none", ""

        if wallet_pence > 0:
            return "none", "Package exhausted — launches can use wallet balance"

        if pending_overage_pence > 0:
            return "extra_usage_invoiced", "Extra usage will be invoiced"

        if has_subscription:
            return "extra_usage_invoiced", "Extra usage will be invoiced via Direct Debit when you launch"

        return "top_up_wallet", "Top up wallet to continue"

    @staticmethod
    def _build_next_invoice(
        db: Session,
        org: Organisation,
        *,
        sub,
        plan,
    ) -> dict[str, Any]:
        from app.services.provider_settings import ProviderSettingsService

        currency = resolve_org_currency(db, org)
        gc_cfg, gc_enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="gocardless")
        gc_available = bool(gc_enabled and str(gc_cfg.get("access_token") or "").strip())
        mandate_id = BillingService.resolve_org_mandate_id(db, org.id) if sub else None
        can_update_mandate = bool(
            gc_available
            and sub is not None
            and str(sub.payment_provider or "").strip().lower() == "gocardless"
            and mandate_id
        )

        empty = {
            "amount_pence": None,
            "amount_display": "—",
            "charge_date": None,
            "charge_date_display": "—",
            "payment_method_label": "—",
            "can_update_mandate": can_update_mandate,
        }

        if sub is None or plan is None:
            return empty

        from app.services.billing_finance_service import BillingFinanceService

        try:
            BillingFinanceService.sync_subscription_billing_fields(db, sub, org=org, plan=plan, commit=True)
        except Exception:
            pass

        from app.models.billing_refund_review import BillingRefundReview
        from app.services.subscription_cancellation_service import (
            CANCELLATION_CANCELLED,
            REVIEW_APPROVED,
            REVIEW_COMPLETED,
        )

        cancel_status = str(getattr(sub, "cancellation_status", "") or "").lower()
        latest_review = (
            db.execute(
                select(BillingRefundReview)
                .where(BillingRefundReview.org_id == org.id)
                .order_by(BillingRefundReview.requested_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        review_stops_renewal = latest_review is not None and str(latest_review.review_status or "").lower() in {
            REVIEW_APPROVED,
            REVIEW_COMPLETED,
        }
        if cancel_status == CANCELLATION_CANCELLED or review_stops_renewal:
            return {
                "amount_pence": 0,
                "amount_display": money_display(0, currency),
                "charge_date": None,
                "charge_date_display": "No renewal",
                "payment_method_label": BillingMonitorService._resolve_payment_method_label(db, sub, mandate_id=mandate_id),
                "can_update_mandate": can_update_mandate,
            }

        sub_status = str(sub.status or "").strip().lower()
        if sub_status not in {"active", "trial", "past_due", "pending_first_payment"}:
            return empty

        rates = PlanPriceService.rates_for_org(db, org, plan=plan)
        amount_pence = int(
            sub.amount_next_payment_minor
            or rates.get("monthly_price_minor")
            or getattr(plan, "price_gbp_pence", None)
            or 0
        )
        charge_dt = (
            getattr(sub, "next_billing_date", None)
            or getattr(sub, "current_period_end", None)
        )
        charge_date = charge_dt.isoformat() if charge_dt else None
        charge_date_display = "—"
        if charge_dt:
            try:
                charge_date_display = charge_dt.strftime("%d %b %Y")
            except Exception:
                charge_date_display = str(charge_dt)

        payment_method_label = BillingMonitorService._resolve_payment_method_label(db, sub, mandate_id=mandate_id)
        if payment_method_label == "—":
            provider = str(getattr(sub, "payment_provider", None) or "").strip().lower()
            if provider == "stripe":
                payment_method_label = "Card · Stripe"
            elif provider == "wallet":
                payment_method_label = "Wallet"
            elif provider:
                payment_method_label = provider.replace("_", " ").title()

        return {
            "amount_pence": amount_pence if amount_pence > 0 else None,
            "amount_display": money_display(amount_pence, currency) if amount_pence > 0 else "—",
            "charge_date": charge_date,
            "charge_date_display": charge_date_display,
            "payment_method_label": payment_method_label or "—",
            "can_update_mandate": can_update_mandate,
            "setup_payment_method_url": "/account/packages" if not can_update_mandate else None,
        }

    @staticmethod
    def _resolve_payment_method_label(db: Session, sub, *, mandate_id: str | None = None) -> str:
        provider = str(getattr(sub, "payment_provider", None) or "").strip().lower()
        if provider != "gocardless":
            return "—"
        mid = str(mandate_id or getattr(sub, "mandate_id", None) or "").strip()
        if not mid:
            mid = BillingService.resolve_org_mandate_id(db, sub.org_id) or ""
        if not mid:
            return "Direct Debit · GoCardless"
        try:
            config = BillingService._get_gocardless_config(db)
            headers = BillingService._gocardless_headers(config["access_token"])
            with httpx.Client(timeout=15) as client:
                mandate_resp = client.get(f"{config['api_base']}/mandates/{mid}", headers=headers)
            if mandate_resp.status_code >= 400:
                return "Direct Debit · GoCardless"
            mandate_payload = mandate_resp.json().get("mandates") or {}
            bank_id = str((mandate_payload.get("links") or {}).get("customer_bank_account") or "").strip()
            if not bank_id:
                return "Direct Debit · GoCardless"
            with httpx.Client(timeout=15) as client:
                bank_resp = client.get(f"{config['api_base']}/customer_bank_accounts/{bank_id}", headers=headers)
            if bank_resp.status_code >= 400:
                return "Direct Debit · GoCardless"
            bank_payload = bank_resp.json().get("customer_bank_accounts") or {}
            ending = str(bank_payload.get("account_number_ending") or "").strip()
            if ending:
                return f"Direct Debit · •• {ending}"
        except Exception:
            pass
        return "Direct Debit · GoCardless"

    @staticmethod
    def build_for_org(
        db: Session,
        org: Organisation,
        *,
        usage_row: OrgUsagePeriod | None = None,
        pending_overage_pence: int | None = None,
    ) -> dict[str, Any]:
        if usage_row is None:
            usage_row = UsageWalletService.get_current(db, org.id)

        currency = resolve_org_currency(db, org)
        wallet_pence = int(org.wallet_balance_pence or 0)
        promo = OrgServiceCreditService.balances_dict(org)
        sub = BillingService.get_subscription(db, org.id)
        plan = BillingService.resolve_active_plan(db, org.id)

        rates: dict[str, Any] = {}
        try:
            rates = PlanPriceService.rates_for_org(db, org, plan=plan)
        except Exception:
            rates = {"currency": currency, "wa_package_fee_minor": 50, "interview_per_min_minor": 35, "wa_extra_minor": 49}

        wa_unit_minor = int(rates.get("wa_package_fee_minor") or 50)
        per_min_minor = int(rates.get("interview_per_min_minor") or 35)

        entitlement = PackageEntitlementService.for_org(db, org, usage_row)
        shared_pool = bool(entitlement.get("shared_package_pool"))

        summary = UsageWalletService.summary_dict(usage_row, db, org.id) if usage_row else {}
        calls = summary.get("calls") or {}
        wa = summary.get("whatsapp") or {}
        sms = summary.get("sms") or {}

        package_remaining_units = int(entitlement.get("package_remaining") or 0) if shared_pool else 0
        package_used_units = int(entitlement.get("package_used") or 0) if shared_pool else 0
        package_included_units = int(entitlement.get("package_included") or 0) if shared_pool else 0

        package_remaining_pence = package_remaining_units * wa_unit_minor if shared_pool else 0
        package_used_pence = package_used_units * wa_unit_minor if shared_pool else 0
        package_included_pence = package_included_units * wa_unit_minor if shared_pool else 0

        if shared_pool and package_remaining_pence > 0:
            primary_source = "package"
            est_wa = package_remaining_units
            est_ai = package_remaining_units
            estimate_source = "package"
            estimate_label = "Estimated from plan"
        elif wallet_pence > 0:
            primary_source = "wallet"
            est_wa, est_ai = BillingMonitorService._wallet_capacity_estimates(
                wallet_pence,
                wa_unit_minor=wa_unit_minor,
                per_min_minor=per_min_minor,
            )
            estimate_source = "wallet"
            estimate_label = "Estimated from wallet"
        else:
            primary_source = "none"
            est_wa = 0
            est_ai = 0
            estimate_source = "none"
            estimate_label = ""

        if pending_overage_pence is None and usage_row is not None:
            total_overage = UsageWalletService._calc_overage_pence(usage_row, db, org.id)
            pending_overage_pence = max(0, total_overage - int(usage_row.overage_invoiced_pence or 0))
        pending_overage_pence = int(pending_overage_pence or 0)

        usage_pct = float(entitlement.get("package_percent") or 0) if shared_pool else max(
            float(calls.get("percent") or 0),
            float(wa.get("percent") or 0),
            float(sms.get("percent") or 0),
        )
        overage_risk = usage_pct >= 80 or pending_overage_pence > 0 or float(summary.get("estimated_overage_gbp") or 0) > 0

        sub_status = str(sub.status or "").strip().lower() if sub else ""
        if sub_status in {"past_due", "suspended"}:
            payment_status = sub_status.replace("_", " ").title()
        elif pending_overage_pence > 0:
            payment_status = "Overage pending"
        elif sub_status:
            payment_status = sub_status.replace("_", " ").title()
        elif wallet_pence > 0:
            payment_status = "Pay as you go"
        else:
            payment_status = "No active plan"

        access = BillingAccessService.access_summary(db, org)
        next_action, next_action_label = BillingMonitorService._resolve_next_action(
            package_remaining_pence=package_remaining_pence,
            wallet_pence=wallet_pence,
            has_subscription=sub is not None and sub_status in {"active", "trial", "past_due", "pending_first_payment"},
            pending_overage_pence=pending_overage_pence,
            can_launch=bool(access.get("can_launch")),
            launch_block_reason=access.get("launch_block_reason"),
        )

        open_invoices = BillingMonitorService._open_invoices_count(db, org.id)

        next_invoice = BillingMonitorService._build_next_invoice(db, org, sub=sub, plan=plan)

        return {
            "shared_package_pool": shared_pool,
            "currency": currency,
            "commercial": {
                "package_remaining_pence": package_remaining_pence,
                "package_remaining_display": money_display(package_remaining_pence, currency),
                "package_used_pence": package_used_pence,
                "package_used_display": money_display(package_used_pence, currency),
                "package_included_pence": package_included_pence,
                "package_included_display": money_display(package_included_pence, currency),
                "package_remaining_units": package_remaining_units,
                "package_used_units": package_used_units,
                "package_included_units": package_included_units,
                "wallet_balance_pence": wallet_pence,
                "wallet_balance_display": money_display(wallet_pence, currency),
                "primary_source": primary_source,
            },
            "capacity_estimates": {
                "estimated_wa_surveys": est_wa,
                "estimated_ai_minutes": est_ai,
                "source": estimate_source,
                "label": estimate_label,
                "disclaimer": ESTIMATE_DISCLAIMER,
            },
            "actual_usage": {
                "whatsapp_used": int(wa.get("used") or 0),
                "calls_used": int(calls.get("used") or 0),
                "sms_used": int(sms.get("used") or 0),
                "survey_credits": int(promo.get("survey_credits") or 0),
                "interview_credits": int(promo.get("interview_credits") or 0),
            },
            "status": {
                "payment_status": payment_status,
                "subscription_status": sub_status or None,
                "billing_period_start": summary.get("period_start"),
                "billing_period_end": summary.get("period_end"),
                "open_invoices_count": open_invoices,
                "overage_pending_pence": pending_overage_pence,
                "overage_pending_display": money_display(pending_overage_pence, currency),
                "overage_risk": overage_risk,
                "usage_pct": round(usage_pct, 1),
                "next_action": next_action,
                "next_action_label": next_action_label,
                "can_launch": bool(access.get("can_launch")),
                "launch_block_reason": access.get("launch_block_reason"),
                "next_invoice": next_invoice,
            },
            "plan_name": plan.name if plan else None,
            "plan_code": str(plan.code or "").strip().lower() if plan else (str(usage_row.plan_code or "").strip().lower() if usage_row else None),
        }

    @staticmethod
    def flatten_for_admin(monitor: dict[str, Any]) -> dict[str, Any]:
        """Flatten monitor payload for admin list/detail rows."""
        commercial = monitor.get("commercial") or {}
        estimates = monitor.get("capacity_estimates") or {}
        actual = monitor.get("actual_usage") or {}
        status = monitor.get("status") or {}
        return {
            "shared_package_pool": bool(monitor.get("shared_package_pool")),
            "package_remaining_pence": int(commercial.get("package_remaining_pence") or 0),
            "package_remaining_display": commercial.get("package_remaining_display"),
            "package_used_pence": int(commercial.get("package_used_pence") or 0),
            "package_used_display": commercial.get("package_used_display"),
            "package_included_pence": int(commercial.get("package_included_pence") or 0),
            "package_included_display": commercial.get("package_included_display"),
            "package_remaining_units": int(commercial.get("package_remaining_units") or 0),
            "package_used_units": int(commercial.get("package_used_units") or 0),
            "package_included_units": int(commercial.get("package_included_units") or 0),
            "wallet_pence": int(commercial.get("wallet_balance_pence") or 0),
            "wallet_display": commercial.get("wallet_balance_display"),
            "primary_source": commercial.get("primary_source"),
            "estimated_wa_surveys": int(estimates.get("estimated_wa_surveys") or 0),
            "estimated_ai_minutes": int(estimates.get("estimated_ai_minutes") or 0),
            "estimate_source": estimates.get("source"),
            "estimate_label": estimates.get("label"),
            "calls_used": int(actual.get("calls_used") or 0),
            "wa_used": int(actual.get("whatsapp_used") or 0),
            "sms_used": int(actual.get("sms_used") or 0),
            "survey_credits": int(actual.get("survey_credits") or 0),
            "interview_credits": int(actual.get("interview_credits") or 0),
            "payment_status": status.get("payment_status"),
            "open_invoices_count": int(status.get("open_invoices_count") or 0),
            "overage_risk": bool(status.get("overage_risk")),
            "usage_pct": status.get("usage_pct"),
            "next_action": status.get("next_action"),
            "next_action_label": status.get("next_action_label"),
            "billing_start": status.get("billing_period_start"),
            "billing_end": status.get("billing_period_end"),
            "estimated_overage_gbp": round(int(status.get("overage_pending_pence") or 0) / 100, 2),
        }
