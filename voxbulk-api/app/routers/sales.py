"""Salesman + Partner Channel portal API. Used by the dashboard Sales / Partner Channel sections."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.models.sales_rep import SalesRep
from app.services.sales_rep_service import SalesRepError, SalesRepService

router = APIRouter(prefix="/sales", tags=["sales"])


def _require_rep(db: Session, principal) -> SalesRep:
    rep = SalesRepService.get_rep_for_user(db, user_id=principal.user_id)
    if rep is None or not rep.is_active:
        raise HTTPException(status_code=403, detail="This account is not an active sales or partner channel user.")
    return rep


def _require_salesman(db: Session, principal) -> SalesRep:
    rep = _require_rep(db, principal)
    if not SalesRepService.is_salesman(rep):
        raise HTTPException(status_code=403, detail="Customer CRM is only available to salesmen.")
    return rep


def _require_partner(db: Session, principal) -> SalesRep:
    rep = _require_rep(db, principal)
    if not SalesRepService.is_partner_channel(rep):
        raise HTTPException(status_code=403, detail="This action is only available to Partner Channel accounts.")
    return rep


@router.get("/me")
def sales_me(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    rep = _require_rep(db, principal)
    return {"ok": True, "rep": SalesRepService.rep_to_dict(rep)}


@router.get("/customers")
def list_customers(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    rep = _require_salesman(db, principal)
    return {"ok": True, "items": SalesRepService.list_customers(db, rep_id=rep.id)}


@router.post("/customers")
def upsert_customer(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    rep = _require_salesman(db, principal)
    try:
        cust = SalesRepService.upsert_customer(db, rep_id=rep.id, payload=payload or {})
    except SalesRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "customer": SalesRepService.customer_to_dict(cust)}


@router.get("/customers/{customer_id}")
def get_customer(customer_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    rep = _require_salesman(db, principal)
    detail = SalesRepService.get_customer_detail(db, rep_id=rep.id, customer_id=customer_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"ok": True, "customer": detail}


@router.delete("/customers/{customer_id}")
def delete_customer(customer_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    rep = _require_salesman(db, principal)
    try:
        SalesRepService.delete_customer(db, rep_id=rep.id, customer_id=customer_id)
    except SalesRepError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"ok": True}


@router.post("/customers/{customer_id}/offer")
def send_offer(customer_id: str, payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    rep = _require_salesman(db, principal)
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
    rep = _require_salesman(db, principal)
    cust = SalesRepService.get_customer(db, rep_id=rep.id, customer_id=customer_id)
    if cust is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return SalesRepService.send_demo_wa(db, customer=cust)


@router.post("/customers/{customer_id}/demo-call")
def demo_call(customer_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    rep = _require_salesman(db, principal)
    cust = SalesRepService.get_customer(db, rep_id=rep.id, customer_id=customer_id)
    if cust is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return SalesRepService.send_demo_call(db, rep=rep, customer=cust)


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    rep = _require_rep(db, principal)
    return {"ok": True, "stats": SalesRepService.dashboard_stats(db, rep)}


@router.get("/partner/offer-template.xlsx")
def partner_offer_template(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_partner(db, principal)
    try:
        content = SalesRepService.partner_offer_template_xlsx()
    except SalesRepError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="partner-offer-contacts.xlsx"'},
    )


@router.post("/partner/bulk-offers/preview")
async def partner_bulk_offers_preview(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    _require_partner(db, principal)
    raw = await file.read()
    try:
        parsed = SalesRepService.parse_partner_offer_recipients(raw, filename=file.filename or "")
    except SalesRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return parsed


@router.post("/partner/bulk-offers")
async def partner_bulk_offers(
    file: UploadFile = File(...),
    offer_details: str = Form("Special VoxBulk partner offer"),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    rep = _require_partner(db, principal)
    raw = await file.read()
    try:
        parsed = SalesRepService.parse_partner_offer_recipients(raw, filename=file.filename or "")
        result = SalesRepService.send_bulk_partner_offers(
            db,
            rep=rep,
            recipients=parsed.get("recipients") or [],
            offer_details=offer_details,
        )
    except SalesRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result
