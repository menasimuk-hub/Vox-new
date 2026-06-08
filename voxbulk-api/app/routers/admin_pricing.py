from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_BILLING, require_cap
from app.core.database import get_db
from app.models.organisation import Organisation
from app.models.pricing import OrgCustomPricing, TopupTier
from app.services.plan_admin_service import PlanAdminError, PlanAdminService
from app.services.voxbulk_pricing_service import VoxbulkPricingError, VoxbulkPricingService

router = APIRouter(prefix="/admin/pricing", tags=["admin-pricing"])

_PRICING_SCHEMA_HINT = (
    "Pricing database schema is out of date. On the VPS run: "
    "cd /www/voxbulk/voxbulk-api && source .venv/bin/activate && alembic upgrade head"
)


def _pricing_db_error(exc: Exception) -> HTTPException:
    msg = str(exc).lower()
    if "wa_survey_extra_pence" in msg or "whatsapp_survey_fee_pence" in msg or "unknown column" in msg:
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_PRICING_SCHEMA_HINT)
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc) or "Pricing error")


@router.get("")
def get_pricing_overview(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    VoxbulkPricingService.ensure_seeded(db)
    settings = VoxbulkPricingService.get_settings(db)
    plans = [PlanAdminService.plan_to_dict(p) for p in PlanAdminService.list_plans(db)]
    tiers = [VoxbulkPricingService.topup_tier_to_dict(t, settings=settings) for t in VoxbulkPricingService.list_topup_tiers(db)]
    custom = []
    for row in VoxbulkPricingService.list_custom_pricing(db):
        org = db.get(Organisation, row.org_id)
        custom.append(VoxbulkPricingService.custom_pricing_to_dict(row, org))
    return {
        "settings": VoxbulkPricingService.settings_to_dict(settings),
        "plans": plans,
        "topup_tiers": tiers,
        "custom_pricing": custom,
        "fx_multipliers": VoxbulkPricingService.fx_multipliers(settings),
    }


@router.post("/seed")
def seed_default_pricing(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    VoxbulkPricingService.seed_voxbulk_plans(db)
    return {"ok": True}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    try:
        row = VoxbulkPricingService.get_settings(db)
        return VoxbulkPricingService.settings_to_dict(row)
    except (OperationalError, ProgrammingError) as exc:
        raise _pricing_db_error(exc) from exc


@router.put("/settings")
def update_settings(payload: dict = Body(...), db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    try:
        row = VoxbulkPricingService.update_settings(db, payload)
        return VoxbulkPricingService.settings_to_dict(row)
    except (OperationalError, ProgrammingError) as exc:
        raise _pricing_db_error(exc) from exc


@router.get("/plans")
def list_plans(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    VoxbulkPricingService.ensure_seeded(db)
    settings = VoxbulkPricingService.get_settings(db)
    out = []
    for p in PlanAdminService.list_plans(db):
        base = PlanAdminService.plan_to_dict(p)
        out.append(VoxbulkPricingService.enrich_plan_dict(p, base, settings))
    return out


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
    settings = VoxbulkPricingService.get_settings(db)
    return [VoxbulkPricingService.topup_tier_to_dict(t, settings=settings) for t in VoxbulkPricingService.list_topup_tiers(db)]


@router.post("/topup-tiers")
def create_topup_tier(payload: dict = Body(...), db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    row = VoxbulkPricingService.create_topup_tier(db, payload)
    settings = VoxbulkPricingService.get_settings(db)
    return VoxbulkPricingService.topup_tier_to_dict(row, settings=settings)


@router.put("/topup-tiers/{tier_id}")
def update_topup_tier(tier_id: str, payload: dict = Body(...), db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    row = db.get(TopupTier, tier_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Top-up tier not found")
    row = VoxbulkPricingService.update_topup_tier(db, row, payload)
    settings = VoxbulkPricingService.get_settings(db)
    return VoxbulkPricingService.topup_tier_to_dict(row, settings=settings)


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
    market: str = Query("gbp"),
    duration_min: int = Query(12),
    interview_count: int = Query(100),
    credit_pence: int = Query(5000),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    settings = VoxbulkPricingService.get_settings(db)
    plans = PlanAdminService.list_plans(db, active_only=True)
    estimates = []
    for p in plans:
        if getattr(p, "is_enterprise", False):
            estimates.append({"plan_code": p.code, "plan_name": p.name, "is_enterprise": True})
            continue
        per_min = int(p.overage_per_min_pence or settings.interview_per_min_pence)
        conn = int(settings.connection_fee_pence or 0) if settings.connection_fee_enabled else 0
        est = VoxbulkPricingService.estimate_interview_batch(
            per_min_pence=per_min,
            duration_min=duration_min,
            interview_count=interview_count,
            connection_fee_pence=conn,
            market=market,
            settings=settings,
        )
        estimates.append({"plan_code": p.code, "plan_name": p.name, **est})
    return {
        "market": market,
        "estimates": estimates,
        "topup_breakdown": VoxbulkPricingService.topup_breakdown(
            credit_pence=credit_pence, settings=settings, market=market
        ),
    }
