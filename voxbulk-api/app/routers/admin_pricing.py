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
    from app.services.pricing_fx_service import PricingFxService

    PricingFxService.ensure_seeded(db)
    return {
        "ok": True,
        "fx_rates": PricingFxService.list_rates(db),
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


@router.get("/fx-rates")
def list_fx_rates(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    from app.services.pricing_fx_service import PricingFxService

    return {"ok": True, "base_currency": "GBP", "fx_rates": PricingFxService.list_rates(db)}


@router.put("/fx-rates")
def upsert_fx_rates(payload: dict = Body(...), db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    from app.services.pricing_fx_service import PricingFxError, PricingFxService

    rates = payload.get("rates", payload)
    try:
        rows = PricingFxService.upsert_rates(db, rates)
    except PricingFxError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True, "base_currency": "GBP", "fx_rates": rows}


@router.post("/fx-rates/sync-unit-rates")
def sync_unit_rates_from_gbp(
    payload: dict | None = Body(None),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.services.plan_price_service import PlanPriceService

    force = bool((payload or {}).get("force"))
    rows = PlanPriceService.sync_currency_settings_from_gbp(db, force=force)
    return {
        "ok": True,
        "synced": [PlanPriceService.currency_settings_to_dict(r) for r in rows],
    }


# ------------------------------------------------------------------ per-service packages (Core / Feedback / Expo)


@router.get("/packages")
def list_pricing_packages(
    service_kind: str | None = Query(None),
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    def work() -> dict[str, Any]:
        from app.services.expo.seed_service import ExpoSeedService
        from app.services.pricing_packages_service import PricingPackagesError, PricingPackagesService

        ExpoSeedService.ensure_seeded(db)
        try:
            return PricingPackagesService.list_packages(db, service_kind=service_kind, active_only=active_only)
        except PricingPackagesError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _run_pricing_db(db, work)


@router.post("/packages")
def create_pricing_package(payload: dict = Body(...), db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    def work() -> dict[str, Any]:
        from app.services.pricing_packages_service import PricingPackagesError, PricingPackagesService

        try:
            item = PricingPackagesService.create_package(db, payload)
        except PricingPackagesError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    return _run_pricing_db(db, work)


@router.put("/packages/{plan_id}")
def update_pricing_package(
    plan_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    def work() -> dict[str, Any]:
        from app.services.pricing_packages_service import PricingPackagesError, PricingPackagesService

        try:
            item = PricingPackagesService.update_package(db, plan_id, payload)
        except PricingPackagesError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    return _run_pricing_db(db, work)


@router.put("/packages/{plan_id}/prices")
def upsert_pricing_package_prices(
    plan_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    def work() -> dict[str, Any]:
        from app.services.pricing_packages_service import PricingPackagesError, PricingPackagesService

        prices = payload.get("prices") if isinstance(payload, dict) else None
        if prices is None:
            prices = payload
        try:
            item = PricingPackagesService.upsert_prices(db, plan_id, prices)
        except PricingPackagesError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    return _run_pricing_db(db, work)


@router.delete("/packages/{plan_id}")
def deactivate_pricing_package(plan_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    def work() -> dict[str, Any]:
        from app.services.pricing_packages_service import PricingPackagesError, PricingPackagesService

        try:
            item = PricingPackagesService.deactivate_package(db, plan_id)
        except PricingPackagesError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    return _run_pricing_db(db, work)


# ------------------------------------------------------------------ private org packages


@router.get("/private-packages/defaults")
def private_package_defaults(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    def work() -> dict[str, Any]:
        from app.services.private_packages_service import PrivatePackagesService

        return {"ok": True, **PrivatePackagesService.defaults_payload(db)}

    return _run_pricing_db(db, work)


@router.get("/private-packages")
def list_private_packages(
    service_kind: str | None = Query(None),
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    def work() -> dict[str, Any]:
        from app.services.private_packages_service import PrivatePackagesService

        items = PrivatePackagesService.list_private_packages(db, service_kind=service_kind, active_only=active_only)
        return {"ok": True, "items": items}

    return _run_pricing_db(db, work)


@router.post("/private-packages")
def create_private_package(payload: dict = Body(...), db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    def work() -> dict[str, Any]:
        from app.services.private_packages_service import PrivatePackagesError, PrivatePackagesService

        try:
            item = PrivatePackagesService.create_package(db, payload)
        except PrivatePackagesError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    return _run_pricing_db(db, work)


@router.put("/private-packages/{plan_id}")
def update_private_package(
    plan_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    def work() -> dict[str, Any]:
        from app.services.private_packages_service import PrivatePackagesError, PrivatePackagesService

        try:
            item = PrivatePackagesService.update_package(db, plan_id, payload)
        except PrivatePackagesError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    return _run_pricing_db(db, work)


@router.put("/private-packages/{plan_id}/orgs")
def set_private_package_orgs(
    plan_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    def work() -> dict[str, Any]:
        from app.services.private_packages_service import PrivatePackagesError, PrivatePackagesService

        org_ids = payload.get("org_ids") if isinstance(payload, dict) else None
        if not isinstance(org_ids, list):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="org_ids must be a list")
        try:
            item = PrivatePackagesService.set_orgs(db, plan_id, org_ids, apply_subscription=True)
        except PrivatePackagesError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    return _run_pricing_db(db, work)


@router.delete("/private-packages/{plan_id}")
def deactivate_private_package(plan_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    def work() -> dict[str, Any]:
        from app.services.private_packages_service import PrivatePackagesError, PrivatePackagesService

        try:
            item = PrivatePackagesService.deactivate_package(db, plan_id)
        except PrivatePackagesError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    return _run_pricing_db(db, work)


@router.get("/private-packages/org/{org_id}")
def list_org_private_assignments(org_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    def work() -> dict[str, Any]:
        from app.services.private_packages_service import PrivatePackagesService

        return {"ok": True, "items": PrivatePackagesService.assignments_for_org(db, org_id)}

    return _run_pricing_db(db, work)


# ------------------------------------------------------------------ custom multi-service packages


@router.get("/custom-packages")
def list_custom_packages(
    status_filter: str | None = Query(None, alias="status"),
    active_only: bool = Query(False),
    q: str | None = Query(None),
    service: str | None = Query(None),
    org_id: str | None = Query(None),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    def work() -> dict[str, Any]:
        from app.services.custom_packages_service import CustomPackagesService

        items = CustomPackagesService.list_packages(
            db,
            status=status_filter,
            active_only=active_only,
            q=q,
            service=service,
            org_id=org_id,
        )
        return {"ok": True, "items": items}

    return _run_pricing_db(db, work)


@router.get("/custom-packages/org/{org_id}")
def get_org_custom_package(org_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    def work() -> dict[str, Any]:
        from app.services.custom_packages_service import CustomPackagesService

        return {"ok": True, "item": CustomPackagesService.get_for_org(db, org_id)}

    return _run_pricing_db(db, work)


@router.get("/custom-packages/{package_id}")
def get_custom_package(package_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    def work() -> dict[str, Any]:
        from app.services.custom_packages_service import CustomPackagesError, CustomPackagesService

        try:
            item = CustomPackagesService.get_package(db, package_id)
        except CustomPackagesError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    return _run_pricing_db(db, work)


@router.post("/custom-packages")
def create_custom_package(payload: dict = Body(...), db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    def work() -> dict[str, Any]:
        from app.services.custom_packages_service import CustomPackagesError, CustomPackagesService

        try:
            item = CustomPackagesService.create_package(db, payload if isinstance(payload, dict) else {})
        except CustomPackagesError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    return _run_pricing_db(db, work)


@router.put("/custom-packages/{package_id}")
def update_custom_package(
    package_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    def work() -> dict[str, Any]:
        from app.services.custom_packages_service import CustomPackagesError, CustomPackagesService

        try:
            item = CustomPackagesService.update_package(db, package_id, payload if isinstance(payload, dict) else {})
        except CustomPackagesError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    return _run_pricing_db(db, work)


@router.post("/custom-packages/{package_id}/duplicate")
def duplicate_custom_package(package_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    def work() -> dict[str, Any]:
        from app.services.custom_packages_service import CustomPackagesError, CustomPackagesService

        try:
            item = CustomPackagesService.duplicate_package(db, package_id)
        except CustomPackagesError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    return _run_pricing_db(db, work)


@router.delete("/custom-packages/{package_id}")
def deactivate_custom_package(package_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    def work() -> dict[str, Any]:
        from app.services.custom_packages_service import CustomPackagesError, CustomPackagesService

        try:
            item = CustomPackagesService.deactivate_package(db, package_id)
        except CustomPackagesError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    return _run_pricing_db(db, work)


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
