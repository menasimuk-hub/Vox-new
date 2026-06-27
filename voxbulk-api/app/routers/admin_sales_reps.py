"""Admin API — Salesmen (Task 8). Create/list/update sales reps and view their performance."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.admin_rbac import require_platform_admin
from app.core.database import get_db
from app.models.sales_rep import SalesRep
from app.models.user import User
from app.services.sales_rep_service import SalesRepError, SalesRepService

router = APIRouter(prefix="/admin/sales-reps", tags=["admin-sales-reps"])


@router.get("")
def list_sales_reps(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    return {"ok": True, "items": SalesRepService.list_reps(db)}


@router.post("")
def create_sales_rep(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    try:
        rep = SalesRepService.create_rep(
            db,
            email=payload.get("email", ""),
            password=payload.get("password", ""),
            name=payload.get("name", ""),
            promo_code=payload.get("promo_code", ""),
            country=payload.get("country"),
            caller_id=payload.get("caller_id"),
        )
    except SalesRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    user = db.execute(select(User).where(User.id == rep.user_id)).scalar_one_or_none()
    return {"ok": True, "rep": SalesRepService.rep_to_dict(rep, user)}


def _get_rep(db: Session, rep_id: str) -> SalesRep:
    rep = db.execute(select(SalesRep).where(SalesRep.id == str(rep_id))).scalar_one_or_none()
    if rep is None:
        raise HTTPException(status_code=404, detail="Salesman not found")
    return rep


@router.patch("/{rep_id}")
def update_sales_rep(rep_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    rep = _get_rep(db, rep_id)
    try:
        rep = SalesRepService.update_rep(db, rep=rep, patch=payload or {})
    except SalesRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    user = db.execute(select(User).where(User.id == rep.user_id)).scalar_one_or_none()
    return {"ok": True, "rep": SalesRepService.rep_to_dict(rep, user)}


@router.get("/{rep_id}/customers")
def list_rep_customers(rep_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    rep = _get_rep(db, rep_id)
    return {"ok": True, "items": SalesRepService.list_customers(db, rep_id=rep.id)}


@router.get("/{rep_id}/dashboard")
def rep_dashboard(rep_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    rep = _get_rep(db, rep_id)
    return {"ok": True, "stats": SalesRepService.dashboard_stats(db, rep)}
