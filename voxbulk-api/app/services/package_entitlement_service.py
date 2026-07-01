"""Shared package entitlement — WA survey + AI voice consume one commercial allowance pool."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.org_usage_period import OrgUsagePeriod
from app.models.organisation import Organisation

PAYG_PLAN_CODES = frozenset({"payg", "free", "topup"})


class PackageEntitlementService:
    """Commercial package pool: WhatsApp recipients + AI call minutes share one allowance."""

    @staticmethod
    def shared_pool_active(usage_row: OrgUsagePeriod | None, plan_code: str | None = None) -> bool:
        if usage_row is None:
            return False
        code = str(plan_code or usage_row.plan_code or "").strip().lower()
        if code in PAYG_PLAN_CODES:
            return False
        status = str(usage_row.status or "").strip().lower()
        if status not in {"active", "trial"}:
            return False
        pack = int(usage_row.pack_credits_included or 0)
        calls = int(usage_row.calls_included or 0)
        wa = int(usage_row.whatsapp_included or 0)
        value = int(getattr(usage_row, "allowance_value_included_minor", 0) or 0)
        return pack > 0 or calls > 0 or wa > 0 or value > 0

    @staticmethod
    def package_included_units(usage_row: OrgUsagePeriod | None) -> int:
        if usage_row is None:
            return 0
        pack = int(usage_row.pack_credits_included or 0)
        if pack > 0:
            return pack
        calls = int(usage_row.calls_included or 0)
        wa = int(usage_row.whatsapp_included or 0)
        if calls <= 0 and wa <= 0:
            return 0
        return max(calls, wa)

    @staticmethod
    def package_used_units(usage_row: OrgUsagePeriod | None) -> int:
        if usage_row is None:
            return 0
        return int(usage_row.calls_used or 0) + int(usage_row.whatsapp_used or 0)

    @staticmethod
    def package_remaining_units(usage_row: OrgUsagePeriod | None) -> int:
        included = PackageEntitlementService.package_included_units(usage_row)
        if included <= 0:
            return 0
        return max(0, included - PackageEntitlementService.package_used_units(usage_row))

    @staticmethod
    def for_usage_row(
        usage_row: OrgUsagePeriod | None,
        *,
        plan_code: str | None = None,
    ) -> dict[str, Any]:
        shared = PackageEntitlementService.shared_pool_active(usage_row, plan_code)
        included = PackageEntitlementService.package_included_units(usage_row) if shared else 0
        used = PackageEntitlementService.package_used_units(usage_row) if shared else 0
        remaining = max(0, included - used) if shared else 0
        pct = round((used / included) * 100, 1) if included > 0 else 0.0

        calls_inc = int(usage_row.calls_included or 0) if usage_row else 0
        calls_used = int(usage_row.calls_used or 0) if usage_row else 0
        wa_inc = int(usage_row.whatsapp_included or 0) if usage_row else 0
        wa_used = int(usage_row.whatsapp_used or 0) if usage_row else 0

        if shared:
            channel_calls_remaining = min(max(0, calls_inc - calls_used), remaining)
            channel_wa_remaining = min(max(0, wa_inc - wa_used), remaining)
        else:
            channel_calls_remaining = max(0, calls_inc - calls_used) if calls_inc > 0 else 0
            channel_wa_remaining = max(0, wa_inc - wa_used) if wa_inc > 0 else 0

        return {
            "shared_package_pool": shared,
            "package_included": included,
            "package_used": used,
            "package_remaining": remaining,
            "package_percent": pct,
            "launch_allowance_remaining": remaining if shared else None,
            "calls_included": calls_inc,
            "calls_used": calls_used,
            "calls_remaining": channel_calls_remaining,
            "whatsapp_included": wa_inc,
            "whatsapp_used": wa_used,
            "whatsapp_remaining": channel_wa_remaining,
        }

    @staticmethod
    def for_org(db: Session, org: Organisation, usage_row: OrgUsagePeriod | None = None) -> dict[str, Any]:
        from app.services.gocardless_service import BillingService

        if usage_row is None:
            from app.services.usage_wallet_service import UsageWalletService

            usage_row = UsageWalletService.get_current(db, org.id)
        plan = BillingService.resolve_active_plan(db, org.id)
        plan_code = str(plan.code or "").strip().lower() if plan else None
        if not plan_code and usage_row is not None:
            plan_code = str(usage_row.plan_code or "").strip().lower() or None
        ent = PackageEntitlementService.for_usage_row(usage_row, plan_code=plan_code)
        from app.services.package_value_pool_service import PackageValuePoolService

        value = PackageValuePoolService.snapshot(db, usage_row, org, plan)
        if value.get("value_pool_active"):
            remaining_minor = int(value.get("package_remaining_minor") or 0)
            used_minor = int(value.get("package_used_minor") or 0)
            included_minor = int(value.get("package_included_minor") or 0)
            ent["shared_package_pool"] = True
            ent["value_pool"] = value
            ent["package_included"] = included_minor
            ent["package_used"] = used_minor
            ent["package_remaining"] = remaining_minor
            ent["package_percent"] = float(value.get("package_percent") or 0)
            ent["launch_allowance_remaining"] = remaining_minor
            ent["package_included_display"] = value.get("package_included_display")
            ent["package_used_display"] = value.get("package_used_display")
            ent["package_remaining_display"] = value.get("package_remaining_display")
        return ent

    @staticmethod
    def merge_into_summary(summary: dict[str, Any], entitlement: dict[str, Any]) -> dict[str, Any]:
        """Apply shared-pool remaining values onto a UsageWalletService.summary_dict payload."""
        if not entitlement.get("shared_package_pool"):
            summary["package"] = {"shared_package_pool": False}
            return summary

        summary["package"] = {
            "shared_package_pool": True,
            "included": entitlement["package_included"],
            "used": entitlement["package_used"],
            "remaining": entitlement["package_remaining"],
            "percent": entitlement["package_percent"],
        }
        calls = dict(summary.get("calls") or {})
        wa = dict(summary.get("whatsapp") or {})
        calls["remaining"] = entitlement["calls_remaining"]
        wa["remaining"] = entitlement["whatsapp_remaining"]
        summary["calls"] = calls
        summary["whatsapp"] = wa
        summary["launch_allowance_remaining"] = entitlement["package_remaining"]
        return summary
