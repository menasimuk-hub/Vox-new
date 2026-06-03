"""Combined ATS + estimated AI interview cost per CV for limits and overage display."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder
from app.services.gocardless_service import BillingService
from app.services.interview_ats_billing_service import ats_unit_price_pence
from app.services.interview_cv_email_service import _loads_config
from app.services.voxbulk_pricing_service import VoxbulkPricingService


def _money(pence: int) -> str:
    return f"£{int(pence or 0) / 100:.2f}"


def cv_per_cv_cost_pence(
    db: Session,
    *,
    org_id: str | None = None,
    order: ServiceOrder | None = None,
) -> dict[str, Any]:
    """ATS parse + connection fee + estimated call minutes for one screened CV."""
    plan = BillingService.resolve_active_plan(db, org_id) if org_id else None
    rates = VoxbulkPricingService.resolve_rates_for_org(db, org_id, plan=plan)
    settings = VoxbulkPricingService.get_settings(db)

    duration = int(settings.estimator_default_duration_min or 12)
    if order is not None:
        cfg = _loads_config(order)
        raw_duration = cfg.get("expected_duration_minutes")
        if raw_duration is not None:
            try:
                duration = max(1, int(raw_duration))
            except (TypeError, ValueError):
                pass

    ats = int(ats_unit_price_pence(db) or 0)
    conn = int(rates.get("connection_fee_pence") or 0)
    per_min = int(rates.get("interview_per_min_pence") or 0)
    call_cost = VoxbulkPricingService.interview_call_cost_pence(
        per_min_pence=per_min,
        duration_min=duration,
        connection_fee_pence=conn,
    )
    combined = max(0, ats + call_cost)
    minute_total = per_min * duration

    breakdown = (
        f"{_money(ats)} ATS + {_money(conn)} connection + "
        f"{duration} min × {_money(per_min)}/min"
    )
    unit_detail = f"{_money(combined)} per screening ({breakdown})"

    return {
        "ats_parsing_pence": ats,
        "connection_fee_pence": conn,
        "interview_per_min_pence": per_min,
        "duration_minutes": duration,
        "call_cost_pence": call_cost,
        "ai_screening_pence": call_cost,
        "combined_pence": combined,
        "combined_gbp": _money(combined),
        "combined_label": unit_detail,
        "cost_per_cv_label": f"Cost per screening: {unit_detail}",
        "overage_breakdown": breakdown,
        "overage_unit_detail": unit_detail,
    }
