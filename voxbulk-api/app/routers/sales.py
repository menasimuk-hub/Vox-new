"""Salesman portal API (Task 8). Used by the dashboard Sales section for sales-role users."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.models.sales_rep import SalesRep
from app.services.sales_rep_service import SalesRepError, SalesRepService

router = APIRouter(prefix="/sales", tags=["sales"])


def _require_rep(db: Session, principal) -> SalesRep:
    rep = SalesRepService.get_rep_for_user(db, user_id=principal.user_id)
    if rep is None or not rep.is_active:
        raise HTTPException(status_code=403, detail="This account is not an active salesman.")
    return rep


@router.get("/me")
def sales_me(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    rep = _require_rep(db, principal)
    return {"ok": True, "rep": SalesRepService.rep_to_dict(rep)}


@router.get("/customers")
def list_customers(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    rep = _require_rep(db, principal)
    return {"ok": True, "items": SalesRepService.list_customers(db, rep_id=rep.id)}


@router.post("/customers")
def upsert_customer(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    rep = _require_rep(db, principal)
    try:
        cust = SalesRepService.upsert_customer(db, rep_id=rep.id, payload=payload or {})
    except SalesRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "customer": SalesRepService.customer_to_dict(cust)}


@router.get("/customers/{customer_id}")
def get_customer(customer_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    rep = _require_rep(db, principal)
    detail = SalesRepService.get_customer_detail(db, rep_id=rep.id, customer_id=customer_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"ok": True, "customer": detail}


@router.delete("/customers/{customer_id}")
def delete_customer(customer_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    rep = _require_rep(db, principal)
    try:
        SalesRepService.delete_customer(db, rep_id=rep.id, customer_id=customer_id)
    except SalesRepError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"ok": True}


@router.post("/customers/{customer_id}/offer")
def send_offer(customer_id: str, payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    rep = _require_rep(db, principal)
    cust = SalesRepService.get_customer(db, rep_id=rep.id, customer_id=customer_id)
    if cust is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    channel = str((payload or {}).get("channel") or "").strip().lower()
    if channel not in ("email", "wa"):
        raise HTTPException(status_code=400, detail="channel must be 'email' or 'wa'")
    return SalesRepService.send_offer(
        db, rep=rep, customer=cust, channel=channel, offer_details=(payload or {}).get("offer_details", "")
    )


@router.post("/customers/{customer_id}/demo-wa")
def demo_wa(customer_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    rep = _require_rep(db, principal)
    cust = SalesRepService.get_customer(db, rep_id=rep.id, customer_id=customer_id)
    if cust is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return SalesRepService.send_demo_wa(db, customer=cust)


@router.post("/customers/{customer_id}/demo-call")
def demo_call(customer_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    rep = _require_rep(db, principal)
    cust = SalesRepService.get_customer(db, rep_id=rep.id, customer_id=customer_id)
    if cust is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return SalesRepService.send_demo_call(db, rep=rep, customer=cust)


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    rep = _require_rep(db, principal)
    return {"ok": True, "stats": SalesRepService.dashboard_stats(db, rep)}
