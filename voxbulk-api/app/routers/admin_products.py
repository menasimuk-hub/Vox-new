from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_BILLING, require_cap
from app.core.database import get_db
from sqlalchemy import select

from app.models.customer_feedback import FeedbackPackage
from app.services.plan_admin_service import PlanAdminError, PlanAdminService
from app.services.products_hub_service import ProductsHubService
from app.services.usage_wallet_service import UsageWalletService

router = APIRouter(prefix="/admin/products", tags=["admin-products"])


@router.get("")
def list_products(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    return ProductsHubService.list_catalog(db)


@router.get("/assignable-plans")
def list_assignable_plans(
    product_line: str | None = None,
    market_zone: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    return ProductsHubService.list_assignable_plans(db, product_line=product_line, market_zone=market_zone)


@router.get("/plans")
def list_subscription_plans(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    return [PlanAdminService.plan_to_dict(p) for p in PlanAdminService.list_plans(db)]


@router.get("/plans/active")
def list_active_subscription_plans(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    return [PlanAdminService.plan_to_dict(p) for p in PlanAdminService.list_plans(db, active_only=True)]


@router.post("/plans")
def create_subscription_plan(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    try:
        row = PlanAdminService.create_plan(db, payload)
    except PlanAdminError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PlanAdminService.plan_to_dict(row)


@router.get("/plans/{plan_id}")
def get_subscription_plan(plan_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    row = PlanAdminService.get_plan(db, plan_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return PlanAdminService.plan_to_dict(row)


@router.put("/plans/{plan_id}")
def update_subscription_plan(
    plan_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    row = PlanAdminService.get_plan(db, plan_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    row = PlanAdminService.update_plan(db, row, payload)
    return PlanAdminService.plan_to_dict(row)


@router.post("/plans/{plan_id}/duplicate")
def duplicate_subscription_plan(plan_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    row = PlanAdminService.get_plan(db, plan_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    dup = PlanAdminService.duplicate_plan(db, row)
    return PlanAdminService.plan_to_dict(dup)


@router.patch("/plans/{plan_id}/copy")
def update_plan_copy(
    plan_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    """Marketing copy and active flag only — does not change prices or billing rates."""
    row = PlanAdminService.get_plan(db, plan_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    try:
        row = ProductsHubService.update_plan_copy(db, row, payload)
    except PlanAdminError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    fb_pkg = db.execute(select(FeedbackPackage).where(FeedbackPackage.plan_id == row.id)).scalar_one_or_none()
    enriched = ProductsHubService.enrich_plan_row(db, row, fb_pkg=fb_pkg)
    if enriched is None:
        return PlanAdminService.plan_to_dict(row)
    return enriched


@router.patch("/plans/{plan_id}/active")
def toggle_subscription_plan_active(
    plan_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    row = PlanAdminService.get_plan(db, plan_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    row = PlanAdminService.set_active(db, row, bool(payload.get("is_active")))
    return PlanAdminService.plan_to_dict(row)


@router.delete("/plans/{plan_id}")
def delete_subscription_plan(plan_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    row = PlanAdminService.get_plan(db, plan_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    try:
        PlanAdminService.delete_plan(db, row)
    except PlanAdminError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/usage/rollover")
def rollover_usage_periods(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    """Manually close expired usage periods and open fresh monthly wallets."""
    return {"ok": True, **UsageWalletService.rollover_due_periods(db)}
