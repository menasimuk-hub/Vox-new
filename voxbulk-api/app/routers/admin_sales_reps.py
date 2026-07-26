"""Admin API — Salesmen and Partner Channel Sales. Create/list/update reps and commissions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.admin_rbac import require_platform_admin
from app.core.database import get_db
from app.models.sales_rep import SalesRep
from app.models.user import User
from app.services.sales_rep_service import KIND_SALESMAN, SalesRepError, SalesRepService

router = APIRouter(prefix="/admin/sales-reps", tags=["admin-sales-reps"])


@router.get("")
def list_sales_reps(
    kind: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    try:
        items = SalesRepService.list_reps(db, kind=kind)
    except SalesRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "items": items}


@router.get("/payout-invoices")
def list_payout_invoices(
    rep_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    from app.services.sales_payout_service import SalesPayoutService

    return {"ok": True, "items": SalesPayoutService.list_invoices(db, rep_id=rep_id, status=status)}


@router.get("/payout-invoices/{invoice_id}")
def get_payout_invoice(invoice_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from app.services.sales_payout_service import SalesPayoutService

    inv = SalesPayoutService.get_invoice(db, invoice_id=invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Payout invoice not found")
    rep = db.get(SalesRep, inv.sales_rep_id)
    return {
        "ok": True,
        "invoice": SalesPayoutService.invoice_to_dict(inv),
        "rep": SalesRepService.rep_to_dict(rep) if rep else None,
    }


@router.post("/payout-invoices/{invoice_id}/approve-pay")
def approve_payout_invoice(
    invoice_id: str,
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    from app.services.sales_payout_service import SalesPayoutService

    inv = SalesPayoutService.get_invoice(db, invoice_id=invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Payout invoice not found")
    try:
        inv = SalesPayoutService.approve_and_pay(db, invoice=inv, admin_id=getattr(admin, "id", None))
    except SalesRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "invoice": SalesPayoutService.invoice_to_dict(inv)}


@router.post("/payout-invoices/{invoice_id}/reject")
def reject_payout_invoice(
    invoice_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    from app.services.sales_payout_service import SalesPayoutService

    inv = SalesPayoutService.get_invoice(db, invoice_id=invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Payout invoice not found")
    try:
        inv = SalesPayoutService.reject_invoice(
            db,
            invoice=inv,
            admin_id=getattr(admin, "id", None),
            reason=(payload or {}).get("reason"),
        )
    except SalesRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "invoice": SalesPayoutService.invoice_to_dict(inv)}


@router.post("")
def create_sales_rep(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    body = payload or {}
    payout = body.get("payout") if isinstance(body.get("payout"), dict) else {
        k: body.get(k)
        for k in (
            "payout_method",
            "bank_holder_name",
            "bank_name",
            "bank_sort_code",
            "bank_account_number",
            "bank_address",
            "paypal_email",
        )
        if k in body
    }
    try:
        rep = SalesRepService.create_rep(
            db,
            email=body.get("email", ""),
            password=body.get("password", ""),
            name=body.get("name", ""),
            promo_code=body.get("promo_code", ""),
            country=body.get("country"),
            caller_id=body.get("caller_id"),
            kind=body.get("kind") or KIND_SALESMAN,
            commission_pct=body.get("commission_pct"),
            company_name=body.get("company_name"),
            mobile=body.get("mobile"),
            commission_type=body.get("commission_type"),
            commission_fixed_minor=body.get("commission_fixed_minor"),
            payout=payout or None,
        )
    except SalesRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    user = db.execute(select(User).where(User.id == rep.user_id)).scalar_one_or_none()
    return {"ok": True, "rep": SalesRepService.rep_to_dict(rep, user)}


@router.post("/partner-channel/reset-services")
def reset_partner_channel_services(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    """Reset Partner Channel orgs to normal service defaults (inherit Admin grants; Interview+Survey visible)."""
    return SalesRepService.reset_all_partner_org_services(db)


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


@router.post("/{rep_id}/reset-password")
def reset_sales_rep_password(rep_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    rep = _get_rep(db, rep_id)
    try:
        SalesRepService.reset_password(db, rep=rep, new_password=(payload or {}).get("password", ""))
    except SalesRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


@router.delete("/{rep_id}")
def delete_sales_rep(rep_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    rep = _get_rep(db, rep_id)
    SalesRepService.delete_rep(db, rep=rep)
    return {"ok": True}


@router.post("/{rep_id}/commissions/mark-paid")
def mark_rep_commissions_paid(rep_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    rep = _get_rep(db, rep_id)
    ids = list((payload or {}).get("commission_ids") or [])
    try:
        result = SalesRepService.mark_rep_commissions_paid(db, rep_id=rep.id, commission_ids=ids or None)
    except SalesRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, **result}


@router.post("/commissions/{commission_id}/mark-paid")
def mark_commission_paid(commission_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    try:
        row = SalesRepService.mark_commission_paid(db, commission_id=commission_id, note=(payload or {}).get("note"))
    except SalesRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "commission_id": row.id, "status": row.status}


@router.get("/{rep_id}/customers")
def list_rep_customers(rep_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    rep = _get_rep(db, rep_id)
    return {"ok": True, "items": SalesRepService.list_customers(db, rep_id=rep.id)}


@router.get("/{rep_id}/dashboard")
def rep_dashboard(rep_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    rep = _get_rep(db, rep_id)
    return {"ok": True, "stats": SalesRepService.dashboard_stats(db, rep), "rep": SalesRepService.rep_to_dict(rep)}
