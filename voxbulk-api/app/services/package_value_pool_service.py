"""Value-based package pool — WA and AI minutes burn org-currency minor units at plan rates."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.org_usage_period import OrgUsagePeriod
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.services.billing_currency import money_display
from app.services.plan_price_service import PlanPriceService


SOFT_CAP_MULTIPLIER = 1.1


class PackageValuePoolService:
    @staticmethod
    def value_pool_active(usage_row: OrgUsagePeriod | None) -> bool:
        if usage_row is None:
            return False
        return int(getattr(usage_row, "allowance_value_included_minor", 0) or 0) > 0

    @staticmethod
    def resolve_included_minor(db: Session, org: Organisation | None, plan: Plan | None) -> int:
        if org is None or plan is None:
            return 0
        code = str(plan.code or "").strip().lower()
        if code in {"payg", "free", "topup"}:
            return 0
        try:
            _currency, monthly = PlanPriceService.monthly_minor_for_org(db, org, plan)
            return max(0, int(monthly or 0))
        except Exception:
            return max(0, int(plan.price_gbp_pence or 0))

    @staticmethod
    def rates_for_row(db: Session, org: Organisation | None, plan: Plan | None) -> dict[str, Any]:
        if org is None:
            return {"currency": "GBP", "wa_unit_minor": 50, "per_min_minor": 35}
        try:
            rates = PlanPriceService.rates_for_org(db, org, plan=plan)
            currency = str(rates.get("currency") or "GBP")
            return {
                "currency": currency,
                "wa_unit_minor": int(rates.get("wa_package_fee_minor") or rates.get("wa_extra_minor") or 50),
                "per_min_minor": int(rates.get("interview_per_min_minor") or rates.get("per_min_minor") or 35),
            }
        except Exception:
            return {"currency": "GBP", "wa_unit_minor": 50, "per_min_minor": 35}

    @staticmethod
    def computed_used_minor(
        usage_row: OrgUsagePeriod | None,
        *,
        wa_unit_minor: int,
        per_min_minor: int,
    ) -> int:
        if usage_row is None:
            return 0
        stored = int(getattr(usage_row, "allowance_value_used_minor", 0) or 0)
        if stored > 0:
            return stored
        wa_used = int(usage_row.whatsapp_used or 0)
        calls_used = int(usage_row.calls_used or 0)
        return wa_used * max(0, wa_unit_minor) + calls_used * max(0, per_min_minor)

    @staticmethod
    def snapshot(
        db: Session,
        usage_row: OrgUsagePeriod | None,
        org: Organisation | None,
        plan: Plan | None,
    ) -> dict[str, Any]:
        if usage_row is None or not PackageValuePoolService.value_pool_active(usage_row):
            return {"value_pool_active": False}
        rates = PackageValuePoolService.rates_for_row(db, org, plan)
        currency = str(rates["currency"])
        included = int(getattr(usage_row, "allowance_value_included_minor", 0) or 0)
        used = PackageValuePoolService.computed_used_minor(
            usage_row,
            wa_unit_minor=int(rates["wa_unit_minor"]),
            per_min_minor=int(rates["per_min_minor"]),
        )
        remaining = included - used
        pct = round((used / included) * 100, 1) if included > 0 else 0.0
        return {
            "value_pool_active": True,
            "currency": currency,
            "package_included_minor": included,
            "package_used_minor": used,
            "package_remaining_minor": remaining,
            "package_included_display": money_display(included, currency),
            "package_used_display": money_display(used, currency),
            "package_remaining_display": money_display(remaining, currency),
            "package_percent": pct,
            "wa_unit_minor": int(rates["wa_unit_minor"]),
            "per_min_minor": int(rates["per_min_minor"]),
        }

    @staticmethod
    def apply_wa_burn(row: OrgUsagePeriod, *, units: int, wa_unit_minor: int) -> int:
        burn = max(0, int(units)) * max(0, int(wa_unit_minor))
        row.allowance_value_used_minor = int(getattr(row, "allowance_value_used_minor", 0) or 0) + burn
        return burn

    @staticmethod
    def apply_call_burn(row: OrgUsagePeriod, *, units: int, per_min_minor: int) -> int:
        burn = max(0, int(units)) * max(0, int(per_min_minor))
        row.allowance_value_used_minor = int(getattr(row, "allowance_value_used_minor", 0) or 0) + burn
        return burn

    @staticmethod
    def adjust_value_used(
        row: OrgUsagePeriod,
        *,
        delta_wa_units: int = 0,
        delta_call_units: int = 0,
        wa_unit_minor: int,
        per_min_minor: int,
    ) -> None:
        delta = (int(delta_wa_units) * max(0, int(wa_unit_minor))) + (int(delta_call_units) * max(0, int(per_min_minor)))
        if delta == 0:
            return
        next_used = int(getattr(row, "allowance_value_used_minor", 0) or 0) + delta
        row.allowance_value_used_minor = max(0, next_used)

    @staticmethod
    def soft_cap_minor(included_minor: int) -> int:
        return int(max(0, int(included_minor or 0)) * SOFT_CAP_MULTIPLIER)

    @staticmethod
    def check_soft_cap(
        usage_row: OrgUsagePeriod | None,
        projected_burn_minor: int,
        *,
        wa_unit_minor: int = 0,
        per_min_minor: int = 0,
    ) -> dict[str, Any]:
        if usage_row is None or not PackageValuePoolService.value_pool_active(usage_row):
            return {"allowed": True, "in_grace": False, "reason": None}
        included = int(getattr(usage_row, "allowance_value_included_minor", 0) or 0)
        used = PackageValuePoolService.computed_used_minor(
            usage_row,
            wa_unit_minor=max(0, int(wa_unit_minor)),
            per_min_minor=max(0, int(per_min_minor)),
        )
        projected = used + max(0, int(projected_burn_minor or 0))
        cap = PackageValuePoolService.soft_cap_minor(included)
        if projected <= included:
            return {"allowed": True, "in_grace": False, "reason": None}
        if projected <= cap:
            return {
                "allowed": True,
                "in_grace": True,
                "reason": "Within 110% package grace — extras invoiced when campaigns complete.",
            }
        return {
            "allowed": False,
            "in_grace": False,
            "reason": (
                "Package allowance exceeded 110% grace. Upgrade your plan, top up your wallet, "
                "or wait for the next billing period."
            ),
        }

    @staticmethod
    def in_soft_cap_grace(
        usage_row: OrgUsagePeriod | None,
        *,
        wa_unit_minor: int = 0,
        per_min_minor: int = 0,
    ) -> bool:
        if usage_row is None or not PackageValuePoolService.value_pool_active(usage_row):
            return False
        included = int(getattr(usage_row, "allowance_value_included_minor", 0) or 0)
        if included <= 0:
            return False
        used = PackageValuePoolService.computed_used_minor(
            usage_row,
            wa_unit_minor=max(0, int(wa_unit_minor)),
            per_min_minor=max(0, int(per_min_minor)),
        )
        return included < used <= PackageValuePoolService.soft_cap_minor(included)
