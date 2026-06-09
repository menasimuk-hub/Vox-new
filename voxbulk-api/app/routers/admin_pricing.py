from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_BILLING, require_cap
from app.core.database import get_db
from app.models.organisation import Organisation
from app.models.pricing import OrgCustomPricing, TopupTier
from app.services.plan_admin_service import PlanAdminService
from app.services.pricing_bootstrap_service import (
    PricingBootstrapError,
    ensure_pricing_ready,
    get_pricing_bootstrap_status,
)
from app.services.voxbulk_pricing_service import VoxbulkPricingError, VoxbulkPricingService

logger = logging.getLogger(__name__)
T = TypeVar("T")

router = APIRouter(prefix="/admin/pricing", tags=["admin-pricing"])


def _bootstrap_http_error(exc: Exception) -> HTTPException:
    status_obj = get_pricing_bootstrap_status()
    detail = status_obj.get("error") or str(exc) or "Pricing bootstrap failed"
    step = status_obj.get("step") or "unknown"
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Pricing not ready (step={step}): {detail}",
    )


def _run_pricing_db(db: Session, fn: Callable[[], T]) -> T:
    try:
        ensure_pricing_ready(db)
        return fn()
    except PricingBootstrapError as exc:
        logger.warning("pricing_admin_bootstrap_error: %s", exc)
        raise _bootstrap_http_error(exc) from exc
    except (OperationalError, ProgrammingError) as exc:
        db.rollback()
        logger.warning("pricing_admin_db_error: %s", exc)
        try:
            ensure_pricing_ready(db)
            return fn()
        except Exception as retry_exc:
            raise _bootstrap_http_error(retry_exc) from retry_exc


@router.get("")
def get_pricing_overview(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    def work() -> dict[str, Any]:
        settings = VoxbulkPricingService.get_settings(db)
        plans = [PlanAdminService.plan_to_dict(p) for p in PlanAdminService.list_plans(db)]
        tiers = [VoxbulkPricingService.topup_tier_to_dict(t, settings=settings) for t in VoxbulkPricingService.list_topup_tiers(db)]
        custom = []
        for row in VoxbulkPricingService.list_custom_pricing(db):
            org = db.get(Organisation, row.org_id)
            custom.append(VoxbulkPricingService.custom_pricing_to_dict(row, org))
        from app.services.billing_currency import SUPPORTED_CURRENCIES

        return {
            "settings": VoxbulkPricingService.settings_to_dict(settings),
            "plans": plans,
            "topup_tiers": tiers,
            "custom_pricing": custom,
            "supported_currencies": list(SUPPORTED_CURRENCIES),
        }

    return _run_pricing_db(db, work)


@router.post("/seed")
def seed_default_pricing(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    def work() -> dict[str, bool]:
        VoxbulkPricingService.seed_voxbulk_plans(db)
        ensure_pricing_ready(db)
        return {"ok": True}

    return _run_pricing_db(db, work)


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    def work() -> dict[str, Any]:
        row = VoxbulkPricingService.get_settings(db)
        return VoxbulkPricingService.settings_to_dict(row)

    return _run_pricing_db(db, work)


@router.put("/settings")
def update_settings(payload: dict = Body(...), db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    def work() -> dict[str, Any]:
        row = VoxbulkPricingService.update_settings(db, payload)
        return VoxbulkPricingService.settings_to_dict(row)

    return _run_pricing_db(db, work)


@router.get("/plans")
def list_plans(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    def work() -> list[dict[str, Any]]:
        settings = VoxbulkPricingService.get_settings(db)
        out = []
        for p in PlanAdminService.list_plans(db):
            base = PlanAdminService.plan_to_dict(p)
            out.append(VoxbulkPricingService.enrich_plan_dict(p, base, settings))
        return out

    return _run_pricing_db(db, work)


@router.put("/plans/{plan_id}")
def update_plan(plan_id: str, payload: dict = Body(...), db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    row = PlanAdminService.get_plan(db, plan_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    if payload.get("is_featured"):
        for p in PlanAdminService.list_plans(db):
            if p.id != plan_id:
                p.is_featured = False
        db.commit()
    row = PlanAdminService.update_plan(db, row, payload)
    settings = VoxbulkPricingService.get_settings(db)
    return VoxbulkPricingService.enrich_plan_dict(row, PlanAdminService.plan_to_dict(row), settings)


@router.get("/topup-tiers")
def list_topup_tiers(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    def work() -> list[dict[str, Any]]:
        settings = VoxbulkPricingService.get_settings(db)
        return [VoxbulkPricingService.topup_tier_to_dict(t, settings=settings) for t in VoxbulkPricingService.list_topup_tiers(db)]

    return _run_pricing_db(db, work)


@router.post("/topup-tiers")
def create_topup_tier(payload: dict = Body(...), db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    def work() -> dict[str, Any]:
        row = VoxbulkPricingService.create_topup_tier(db, payload)
        settings = VoxbulkPricingService.get_settings(db)
        return VoxbulkPricingService.topup_tier_to_dict(row, settings=settings)

    return _run_pricing_db(db, work)


@router.put("/topup-tiers/{tier_id}")
def update_topup_tier(tier_id: str, payload: dict = Body(...), db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    row = db.get(TopupTier, tier_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Top-up tier not found")

    def work() -> dict[str, Any]:
        updated = VoxbulkPricingService.update_topup_tier(db, row, payload)
        settings = VoxbulkPricingService.get_settings(db)
        return VoxbulkPricingService.topup_tier_to_dict(updated, settings=settings)

    return _run_pricing_db(db, work)


@router.delete("/topup-tiers/{tier_id}")
def delete_topup_tier(tier_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    row = db.get(TopupTier, tier_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Top-up tier not found")
    VoxbulkPricingService.delete_topup_tier(db, row)
    return {"ok": True}


@router.get("/custom")
def list_custom_pricing(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    out = []
    for row in VoxbulkPricingService.list_custom_pricing(db):
        org = db.get(Organisation, row.org_id)
        out.append(VoxbulkPricingService.custom_pricing_to_dict(row, org))
    return out


@router.post("/custom")
def create_custom_pricing(payload: dict = Body(...), db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    try:
        row = VoxbulkPricingService.create_custom_pricing(db, payload)
    except VoxbulkPricingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    org = db.get(Organisation, row.org_id)
    return VoxbulkPricingService.custom_pricing_to_dict(row, org)


@router.put("/custom/{pricing_id}")
def update_custom_pricing(
    pricing_id: str, payload: dict = Body(...), db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))
):
    row = db.get(OrgCustomPricing, pricing_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom pricing not found")
    row = VoxbulkPricingService.update_custom_pricing(db, row, payload)
    org = db.get(Organisation, row.org_id)
    return VoxbulkPricingService.custom_pricing_to_dict(row, org)


@router.delete("/custom/{pricing_id}")
def delete_custom_pricing(pricing_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    row = db.get(OrgCustomPricing, pricing_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom pricing not found")
    VoxbulkPricingService.delete_custom_pricing(db, row)
    return {"ok": True}


@router.get("/preview")
def pricing_preview(
    currency: str = Query("GBP"),
    duration_min: int = Query(12),
    interview_count: int = Query(100),
    credit_pence: int = Query(5000),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    def work() -> dict[str, Any]:
        from app.services.plan_price_service import PlanPriceService

        settings = VoxbulkPricingService.get_settings(db)
        unit = PlanPriceService.get_currency_settings(db, currency)
        plans = PlanAdminService.list_plans(db, active_only=True)
        estimates = []
        for p in plans:
            if getattr(p, "is_enterprise", False):
                estimates.append({"plan_code": p.code, "plan_name": p.name, "is_enterprise": True})
                continue
            price = PlanPriceService.get_price(db, p.id, currency)
            per_min = int(price.per_min_minor or 0) if price else int(unit.interview_per_min_minor or 0)
            conn = int(unit.connection_fee_minor or 0)
            est = VoxbulkPricingService.estimate_interview_batch(
                per_min_pence=per_min,
                duration_min=duration_min,
                interview_count=interview_count,
                connection_fee_pence=conn,
                currency=currency,
            )
            estimates.append({"plan_code": p.code, "plan_name": p.name, **est})
        return {
            "currency": currency.upper(),
            "estimates": estimates,
            "topup_breakdown": VoxbulkPricingService.topup_breakdown(
                credit_pence=credit_pence, settings=settings, currency=currency
            ),
        }

    return _run_pricing_db(db, work)


# ------------------------------------------------------------------ per-currency plan prices


@router.get("/plan-prices")
def list_all_plan_prices(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    def work() -> dict[str, Any]:
        from app.services.billing_currency import SUPPORTED_CURRENCIES
        from app.services.plan_price_service import PlanPriceService

        PlanPriceService.ensure_seeded(db)
        plans = PlanAdminService.list_plans(db)
        out = []
        for p in plans:
            prices = {row.currency: PlanPriceService.price_to_dict(row) for row in PlanPriceService.list_for_plan(db, p.id)}
            out.append(
                {
                    "plan_id": p.id,
                    "plan_code": p.code,
                    "plan_name": p.name,
                    "is_enterprise": bool(getattr(p, "is_enterprise", False)),
                    "is_active": bool(p.is_active),
                    "sort_order": int(p.sort_order or 100),
                    "prices": prices,
                }
            )
        currency_settings = [
            PlanPriceService.currency_settings_to_dict(PlanPriceService.get_currency_settings(db, c))
            for c in SUPPORTED_CURRENCIES
        ]
        return {
            "ok": True,
            "supported_currencies": list(SUPPORTED_CURRENCIES),
            "plans": out,
            "currency_settings": currency_settings,
        }

    return _run_pricing_db(db, work)


@router.put("/plan-prices/{plan_id}/{currency}")
def upsert_plan_price(
    plan_id: str,
    currency: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.services.plan_price_service import PlanPriceError, PlanPriceService

    try:
        row = PlanPriceService.upsert_price(db, plan_id=plan_id, currency=currency, payload=payload)
    except PlanPriceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PlanPriceService.price_to_dict(row)


@router.get("/currency-settings")
def list_currency_settings(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    from app.services.billing_currency import SUPPORTED_CURRENCIES
    from app.services.plan_price_service import PlanPriceService

    return {
        "ok": True,
        "currency_settings": [
            PlanPriceService.currency_settings_to_dict(PlanPriceService.get_currency_settings(db, c))
            for c in SUPPORTED_CURRENCIES
        ],
    }


@router.put("/currency-settings/{currency}")
def update_currency_settings(
    currency: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.services.plan_price_service import PlanPriceError, PlanPriceService

    try:
        row = PlanPriceService.update_currency_settings(db, currency, payload)
    except PlanPriceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PlanPriceService.currency_settings_to_dict(row)


# ------------------------------------------------------------------ billing settings (company / VAT / invoice numbering)


@router.get("/billing-settings")
def get_billing_settings(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    from app.services.billing_settings_service import BillingSettingsService

    return BillingSettingsService.to_dict(BillingSettingsService.get(db))


@router.put("/billing-settings")
def update_billing_settings(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.services.billing_settings_service import BillingSettingsService

    try:
        row = BillingSettingsService.update(db, payload)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return BillingSettingsService.to_dict(row)
