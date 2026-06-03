"""Per-campaign CV email collection limits, defaults, and overage handling."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.plan import Plan
from app.models.service_order import ServiceOrder
from app.services.gocardless_service import BillingService
from app.services.interview_cv_exclusion_service import (
    cv_accepted_recipient_count,
    cv_min_ats_score_from_config,
)
from app.services.interview_cv_screening_pricing import cv_per_cv_cost_pence
from app.services.interview_cv_email_service import _loads_config
from app.services.usage_wallet_service import UsageWalletService

logger = logging.getLogger(__name__)


class CvCollectionConfigError(ValueError):
    pass


def cv_max_count_from_config(cfg: dict[str, Any]) -> int | None:
    raw = cfg.get("cv_max_count")
    if raw is None:
        return None
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return None


def is_cv_email_active_campaign(order: ServiceOrder, *, now: datetime | None = None) -> bool:
    cfg = _loads_config(order)
    if not cfg.get("cv_email_enabled"):
        return False
    from app.services.interview_cv_email_service import cv_collection_complete

    return not cv_collection_complete(order, now=now)


def order_reserves_cv_allocation(
    db: Session,
    order: ServiceOrder,
    *,
    now: datetime | None = None,
) -> bool:
    """Reserve plan pool only when collection is open or CVs were already received."""
    if not is_cv_email_active_campaign(order, now=now):
        return False
    max_c = cv_max_count_from_config(_loads_config(order))
    if max_c is None or max_c <= 0:
        return False
    from app.services.interview_cv_email_service import cv_email_window_state

    if cv_email_window_state(order, now=now) == "open":
        return True
    return cv_accepted_recipient_count(db, order) > 0


def _resolve_org_cv_allowances(
    db: Session,
    org_id: str,
) -> tuple[Plan | None, OrgUsagePeriod | None, int, int]:
    """Return plan, usage row, plan_included cv scans, period_used."""
    from app.models.org_usage_period import OrgUsagePeriod
    from app.models.plan import Plan
    from app.services.voxbulk_pricing_service import VoxbulkPricingService

    plan = BillingService.resolve_active_plan(db, org_id)
    sub = BillingService.get_subscription(db, org_id)
    row = UsageWalletService.get_current(db, org_id)

    if plan is not None and sub is not None and str(sub.status or "").lower() in {"active", "trial", "past_due"}:
        settings = VoxbulkPricingService.get_settings(db)
        if not getattr(plan, "is_enterprise", False):
            VoxbulkPricingService.apply_plan_allowances(db, plan, settings)
            db.refresh(plan)
        if row is None:
            row = UsageWalletService.bootstrap_from_plan(db, org_id=org_id, subscription=sub)
        elif int(getattr(row, "cv_scans_included", 0) or 0) != int(getattr(plan, "cv_scans_included", 0) or 0):
            UsageWalletService.sync_plan_limits(db, org_id=org_id, plan=plan, subscription=sub)
            row = UsageWalletService.get_current(db, org_id)

    period_used = int(getattr(row, "cv_scans_used", 0) or 0) if row is not None else 0

    if plan is not None:
        plan_included = int(getattr(plan, "cv_scans_included", 0) or 0)
        if plan_included <= 0 and not getattr(plan, "is_enterprise", False):
            settings = VoxbulkPricingService.get_settings(db)
            calc = VoxbulkPricingService.compute_plan_allowances(plan, settings)
            plan_included = int(calc.get("cv_scans_included") or 0)
    elif row is not None:
        plan_included = int(getattr(row, "cv_scans_included", 0) or 0)
    else:
        plan_included = 0

    return plan, row, plan_included, period_used


def compute_cv_collection_limits(
    db: Session,
    org_id: str,
    *,
    exclude_order_id: str | None = None,
) -> dict[str, Any]:
    plan, row, plan_included, period_used = _resolve_org_cv_allowances(db, org_id)

    unlimited = bool(plan is not None and getattr(plan, "is_enterprise", False))
    plan_balance_remaining: int | None = None if unlimited else max(0, plan_included - period_used)

    reserved = 0
    orders = (
        db.execute(
            select(ServiceOrder).where(
                ServiceOrder.org_id == org_id,
                ServiceOrder.service_code == "interview",
            )
        )
        .scalars()
        .all()
    )
    now = datetime.utcnow()
    own_order = db.get(ServiceOrder, exclude_order_id) if exclude_order_id else None
    for other in orders:
        if exclude_order_id and other.id == exclude_order_id:
            continue
        if not order_reserves_cv_allocation(db, other, now=now):
            continue
        max_c = cv_max_count_from_config(_loads_config(other))
        if max_c is not None:
            reserved += max_c

    if unlimited:
        remaining: int | None = None
        default_max: int | None = None
    else:
        remaining = max(0, int(plan_balance_remaining or 0) - reserved)
        default_max = remaining

    unit = cv_per_cv_cost_pence(db, org_id=org_id, order=own_order)
    combined = int(unit["combined_pence"] or 0)
    result = {
        "plan_included": plan_included,
        "period_used": period_used,
        "plan_balance_remaining": plan_balance_remaining,
        "reserved_across_active": reserved,
        "remaining": remaining,
        "unlimited": unlimited,
        "default_max_cvs": default_max,
        "ats_parsing_pence": unit["ats_parsing_pence"],
        "ai_screening_pence": unit["ai_screening_pence"],
        "combined_pence": combined,
        "combined_gbp": unit["combined_gbp"],
        "combined_label": unit["combined_label"],
        "cost_per_cv_label": unit["cost_per_cv_label"],
        "overage_breakdown": unit.get("overage_breakdown"),
        "overage_unit_detail": unit.get("overage_unit_detail"),
        "connection_fee_pence": unit.get("connection_fee_pence"),
        "interview_per_min_pence": unit.get("interview_per_min_pence"),
        "duration_minutes": unit.get("duration_minutes"),
        "call_cost_pence": unit.get("call_cost_pence"),
        "overage_unit_price_pence": combined,
        "overage_unit_price_gbp": unit["combined_gbp"],
    }
    if exclude_order_id:
        if unlimited:
            result["available_for_order"] = None
        else:
            result["available_for_order"] = int(remaining or 0)
    return result


def cv_collection_at_capacity(db: Session, order: ServiceOrder) -> bool:
    cfg = _loads_config(order)
    max_c = cv_max_count_from_config(cfg)
    if max_c is None:
        return False
    return cv_accepted_recipient_count(db, order) >= max_c


def cv_screening_credits_available(db: Session, org_id: str) -> bool:
    limits = compute_cv_collection_limits(db, org_id)
    if limits["unlimited"]:
        return True
    remaining = int(limits.get("remaining") or 0)
    period_used = int(limits.get("period_used") or 0)
    plan_included = int(limits.get("plan_included") or 0)
    if plan_included <= 0:
        return True
    return period_used < plan_included and remaining > 0


def close_cv_collection_on_limit(db: Session, order: ServiceOrder, *, now: datetime | None = None) -> ServiceOrder:
    ts = now or datetime.utcnow()
    cfg = _loads_config(order)
    cfg["cv_email_end_at"] = ts.isoformat()
    cfg["cv_collection_end_at"] = ts.isoformat()
    cfg["cv_collection_close_at"] = ts.isoformat()
    cfg["cv_collection_closed_on_limit_at"] = ts.isoformat()
    order.config_json = json.dumps(cfg, ensure_ascii=False)
    order.updated_at = ts
    db.add(order)
    db.commit()
    db.refresh(order)
    logger.info("cv_collection_closed_on_limit order_id=%s recipients=%s", order.id, order.recipient_count)
    return order


def maybe_close_cv_collection_on_limit(db: Session, order: ServiceOrder, *, now: datetime | None = None) -> bool:
    cfg = _loads_config(order)
    if not cfg.get("cv_email_enabled"):
        return False
    from app.services.interview_cv_email_service import cv_collection_complete

    if cv_collection_complete(order, now=now):
        return False
    if not bool(cfg.get("cv_auto_close_on_limit", True)):
        return False
    if not cv_collection_at_capacity(db, order):
        return False
    close_cv_collection_on_limit(db, order, now=now)
    return True


def validate_and_apply_cv_config(
    db: Session,
    org_id: str,
    order: ServiceOrder,
    cfg: dict[str, Any],
    *,
    previous_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize CV email advanced settings and enforce overage consent."""
    merged = dict(previous_cfg or _loads_config(order))
    merged.update(cfg)
    cfg = merged

    cfg["cv_min_ats_score"] = cv_min_ats_score_from_config(
        cfg if cfg.get("cv_min_ats_score") is not None else (previous_cfg or {})
    )

    enabled = bool(cfg.get("cv_email_enabled"))
    if not enabled:
        cfg.pop("cv_auto_run_ats", None)
        cfg.pop("cv_auto_run_ats_only_with_credits", None)
        return cfg

    limits = compute_cv_collection_limits(db, org_id, exclude_order_id=order.id)
    now = datetime.utcnow()

    if not cfg.get("cv_collection_start_at") and not cfg.get("cv_email_start_at"):
        cfg["cv_collection_start_at"] = now.isoformat()
        cfg["cv_email_start_at"] = now.isoformat()

    close_at = cfg.get("cv_collection_close_at")
    if close_at is None:
        close_at = cfg.get("cv_collection_end_at") or cfg.get("cv_email_end_at")
    close_at = str(close_at).strip() if close_at else None
    if close_at:
        cfg["cv_collection_close_at"] = close_at
        cfg["cv_collection_end_at"] = close_at
        cfg["cv_email_end_at"] = close_at
    else:
        if not cfg.get("cv_collection_closed_early_at") and not cfg.get("cv_collection_closed_on_limit_at"):
            cfg["cv_collection_close_at"] = None
            cfg["cv_collection_end_at"] = None
            cfg["cv_email_end_at"] = None

    prev_max = cv_max_count_from_config(previous_cfg or {})
    if cfg.get("cv_max_count") is None and prev_max is None:
        if limits["unlimited"]:
            cfg["cv_max_count"] = None
        else:
            cfg["cv_max_count"] = limits["default_max_cvs"]
    elif cfg.get("cv_max_count") is not None:
        try:
            cfg["cv_max_count"] = max(0, int(cfg["cv_max_count"]))
        except (TypeError, ValueError):
            cfg["cv_max_count"] = limits["default_max_cvs"]

    if cfg.get("cv_auto_close_on_limit") is None and (previous_cfg or {}).get("cv_auto_close_on_limit") is None:
        cfg["cv_auto_close_on_limit"] = True
    else:
        cfg["cv_auto_close_on_limit"] = bool(cfg.get("cv_auto_close_on_limit", True))

    cfg.pop("cv_auto_run_ats", None)
    cfg.pop("cv_auto_run_ats_only_with_credits", None)

    if not limits["unlimited"]:
        max_count = cv_max_count_from_config(cfg)
        if max_count is not None:
            available = int(limits.get("available_for_order") or limits.get("remaining") or 0)
            if max_count > available:
                if not cfg.get("cv_overage_acknowledged"):
                    raise CvCollectionConfigError(
                        f"Max CVs ({max_count}) exceeds your remaining plan allowance ({available}). "
                        "Acknowledge overage billing in Advanced settings to continue."
                    )
                extra = max_count - available
                unit = int(limits["overage_unit_price_pence"])
                total = extra * unit
                unit_gbp = unit / 100
                total_gbp = total / 100
                cfg["cv_overage_pending"] = {
                    "extra_count": extra,
                    "unit_price_pence": unit,
                    "total_pence": total,
                    "total_gbp": f"£{total_gbp:.2f}",
                    "ats_parsing_pence": limits.get("ats_parsing_pence"),
                    "connection_fee_pence": limits.get("connection_fee_pence"),
                    "interview_per_min_pence": limits.get("interview_per_min_pence"),
                    "duration_minutes": limits.get("duration_minutes"),
                    "call_cost_pence": limits.get("call_cost_pence"),
                    "ai_screening_pence": limits.get("call_cost_pence"),
                    "combined_label": limits.get("combined_label"),
                    "overage_breakdown": limits.get("overage_breakdown"),
                    "description": (
                        f"{extra} extra screening{'s' if extra != 1 else ''} × "
                        f"£{unit_gbp:.2f} ({limits.get('overage_breakdown') or 'ATS + connection + call minutes'}) "
                        f"= £{total_gbp:.2f} will be added to your next invoice"
                    ),
                    "acknowledged_at": now.isoformat(),
                }
            elif cfg.get("cv_overage_pending") and max_count <= available:
                cfg.pop("cv_overage_pending", None)
                cfg["cv_overage_acknowledged"] = False

    cfg["cv_email_enabled"] = True
    return cfg
