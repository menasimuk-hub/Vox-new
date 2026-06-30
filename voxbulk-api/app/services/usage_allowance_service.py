"""Normalized product allowances for dashboard billing KPIs."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.plan import Plan


class UsageAllowanceService:
    @staticmethod
    def _allowance_row(
        *,
        product: str,
        key: str,
        label: str,
        used: int,
        included: int,
        unit: str,
        unlimited: bool = False,
        period_start: str | None = None,
        period_end: str | None = None,
        remaining_override: int | None = None,
    ) -> dict[str, Any]:
        used_n = max(0, int(used or 0))
        if unlimited:
            remaining = None
            pct = 0.0
        elif included > 0:
            remaining = (
                max(0, int(remaining_override))
                if remaining_override is not None
                else max(0, included - used_n)
            )
            pct = round((used_n / included) * 100, 1)
        else:
            remaining = None
            pct = 0.0
        return {
            "product": product,
            "key": key,
            "label": label,
            "used": used_n,
            "included": int(included or 0),
            "remaining": remaining,
            "unit": unit,
            "unlimited": unlimited,
            "period_start": period_start,
            "period_end": period_end,
            "pct_used": pct,
        }

    @staticmethod
    def _alerts_from_allowances(allowances: list[dict[str, Any]]) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        for row in allowances:
            if row.get("unlimited") or int(row.get("included") or 0) <= 0:
                continue
            pct = float(row.get("pct_used") or 0)
            if pct >= 100:
                level = "critical"
                message = f"{row.get('label')} allowance used up"
            elif pct >= 80:
                level = "warning"
                message = f"Running low on {row.get('label')}"
            else:
                continue
            alerts.append(
                {
                    "product": row.get("product"),
                    "key": row.get("key"),
                    "level": level,
                    "message": message,
                    "pct_used": pct,
                }
            )
        return alerts

    @staticmethod
    def build_core_allowances(
        usage_payload: dict[str, Any] | None,
        *,
        cv_used: int = 0,
        cv_included: int = 0,
        shared_pool: bool = False,
    ) -> list[dict[str, Any]]:
        if not usage_payload:
            return []
        period_start = usage_payload.get("period_start")
        period_end = usage_payload.get("period_end")
        calls = usage_payload.get("calls") or {}
        whatsapp = usage_payload.get("whatsapp") or {}
        rows: list[dict[str, Any]] = [
            UsageAllowanceService._allowance_row(
                product="core",
                key="calls",
                label="AI call minutes",
                used=int(calls.get("used") or 0),
                included=int(calls.get("included") or 0),
                unit="min",
                period_start=None,
                period_end=period_end,
                remaining_override=calls.get("remaining"),
            ),
            UsageAllowanceService._allowance_row(
                product="core",
                key="whatsapp",
                label="WA survey recipients",
                used=int(whatsapp.get("used") or 0),
                included=int(whatsapp.get("included") or 0),
                unit="recipients",
                period_start=None,
                period_end=period_end,
                remaining_override=whatsapp.get("remaining"),
            ),
        ]
        if cv_included > 0:
            cv = usage_payload.get("cv_scans") or {}
            rows.append(
                UsageAllowanceService._allowance_row(
                    product="core",
                    key="cv_scans",
                    label="CV scans",
                    used=int(cv.get("used") or cv_used),
                    included=int(cv.get("included") or cv_included),
                    unit="scans",
                    period_start=period_start,
                    period_end=period_end,
                )
            )
        if shared_pool:
            for row in rows:
                row["shared_pool"] = True
        return rows

    @staticmethod
    def build_feedback_allowances(db: Session, org_id: str) -> list[dict[str, Any]]:
        from app.services.customer_feedback.billing_service import FeedbackBillingService

        sub = FeedbackBillingService.get_active_subscription(db, org_id)
        if sub is None:
            return []
        if str(sub.status or "").lower() not in {"active", "pending_first_payment", "trial"}:
            return []
        usage = FeedbackBillingService.get_current_usage(db, org_id)
        period_end = sub.current_period_end.isoformat() if sub.current_period_end else None
        wa_included = int(usage.get("wa_units_included") or 0)
        wa_used = int(usage.get("wa_units_used") or 0)
        web_included = int(usage.get("web_units_included") or 0)
        web_used = int(usage.get("web_units_used") or 0)
        web_unlimited = web_included < 0
        return [
            UsageAllowanceService._allowance_row(
                product="feedback",
                key="feedback_wa",
                label="WA responses",
                used=wa_used,
                included=wa_included,
                unit="responses",
                period_start=None,
                period_end=period_end,
                remaining_override=int(usage.get("wa_units_remaining") or 0),
            ),
            UsageAllowanceService._allowance_row(
                product="feedback",
                key="feedback_web",
                label="Web surveys",
                used=web_used,
                included=0 if web_unlimited else web_included,
                unit="surveys",
                unlimited=web_unlimited,
                period_start=None,
                period_end=period_end,
                remaining_override=int(usage.get("web_units_remaining") or 0) if not web_unlimited else None,
            ),
        ]

    @staticmethod
    def build_for_org(
        db: Session,
        org: Organisation,
        *,
        usage_payload: dict[str, Any] | None,
        current_plan: Plan | None,
        usage_row,
        shared_pool: bool,
        billing_monitor: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        cv_included = int(getattr(current_plan, "cv_scans_included", 0) or 0) if current_plan else 0
        cv_used = int(getattr(usage_row, "cv_scans_used", 0) or 0) if usage_row else 0
        allowances = UsageAllowanceService.build_core_allowances(
            usage_payload,
            cv_used=cv_used,
            cv_included=cv_included,
            shared_pool=shared_pool,
        )
        allowances.extend(UsageAllowanceService.build_feedback_allowances(db, org.id))
        alerts = UsageAllowanceService._alerts_from_allowances(allowances)
        return allowances, alerts
