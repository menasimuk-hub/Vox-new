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


@router.get("/hub-catalog")
def sales_hub_catalog(
    country: str | None = Query(default=None),
    currency: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    from app.services.billing_currency import currency_for_country_code, normalize_currency
    from app.services.sales_hub_benefits import packages_for_currency, service_catalog

    cur = normalize_currency(currency) if currency else currency_for_country_code(country)
    return {
        "ok": True,
        "currency": cur,
        "services": service_catalog(),
        "packages": packages_for_currency(db, cur),
    }


@router.get("/hub-invoices")
def list_hub_invoices(
    rep_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    from app.services.sales_hub_invoice_service import SalesHubInvoiceService

    return {
        "ok": True,
        "items": SalesHubInvoiceService.list_invoices(db, rep_id=rep_id, status=status, kind=kind),
        "kpis": SalesHubInvoiceService.kpi_totals(db),
    }


@router.post("/hub-invoices")
def create_hub_invoice(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from app.services.sales_hub_invoice_service import SalesHubInvoiceService

    body = payload or {}
    rep_id = str(body.get("sales_rep_id") or body.get("rep_id") or "").strip()
    if not rep_id:
        raise HTTPException(status_code=400, detail="sales_rep_id is required")
    rep = _get_rep(db, rep_id)
    try:
        inv = SalesHubInvoiceService.create(db, rep=rep, payload=body)
        if body.get("send_email"):
            SalesHubInvoiceService.send_email(db, inv=inv, reminder=False)
            inv = SalesHubInvoiceService.get(db, inv.id) or inv
    except SalesRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    items = SalesHubInvoiceService.list_items(db, inv.id)
    return {"ok": True, "invoice": SalesHubInvoiceService.invoice_to_dict(inv, items)}


@router.get("/hub-invoices/{invoice_id}/pdf")
def hub_invoice_pdf(invoice_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from fastapi.responses import Response

    from app.services.sales_hub_invoice_service import SalesHubInvoiceService

    inv = SalesHubInvoiceService.get(db, invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    try:
        pdf = SalesHubInvoiceService.render_pdf_bytes(db, inv)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF failed: {e}") from e
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{inv.number}.pdf"'},
    )


@router.get("/hub-invoices/{invoice_id}")
def get_hub_invoice(invoice_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from app.services.sales_hub_invoice_service import SalesHubInvoiceService

    inv = SalesHubInvoiceService.get(db, invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    items = SalesHubInvoiceService.list_items(db, inv.id)
    rep = db.get(SalesRep, inv.sales_rep_id)
    return {
        "ok": True,
        "invoice": SalesHubInvoiceService.invoice_to_dict(inv, items),
        "rep": SalesRepService.rep_to_dict(rep) if rep else None,
    }


@router.patch("/hub-invoices/{invoice_id}")
def update_hub_invoice(
    invoice_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)
):
    from app.services.sales_hub_invoice_service import SalesHubInvoiceService

    inv = SalesHubInvoiceService.get(db, invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    try:
        inv = SalesHubInvoiceService.update(db, inv=inv, payload=payload or {})
    except SalesRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    items = SalesHubInvoiceService.list_items(db, inv.id)
    return {"ok": True, "invoice": SalesHubInvoiceService.invoice_to_dict(inv, items)}


@router.post("/hub-invoices/{invoice_id}/send")
def send_hub_invoice(invoice_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from app.services.sales_hub_invoice_service import SalesHubInvoiceService

    inv = SalesHubInvoiceService.get(db, invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    try:
        SalesHubInvoiceService.send_email(db, inv=inv, reminder=False)
        inv = SalesHubInvoiceService.get(db, invoice_id) or inv
    except SalesRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    items = SalesHubInvoiceService.list_items(db, inv.id)
    return {"ok": True, "invoice": SalesHubInvoiceService.invoice_to_dict(inv, items)}


@router.post("/hub-invoices/{invoice_id}/remind")
def remind_hub_invoice(invoice_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from app.services.sales_hub_invoice_service import SalesHubInvoiceService

    inv = SalesHubInvoiceService.get(db, invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    try:
        SalesHubInvoiceService.send_email(db, inv=inv, reminder=True)
        inv = SalesHubInvoiceService.get(db, invoice_id) or inv
    except SalesRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    items = SalesHubInvoiceService.list_items(db, inv.id)
    return {"ok": True, "invoice": SalesHubInvoiceService.invoice_to_dict(inv, items)}


@router.post("/hub-invoices/{invoice_id}/mark-paid")
def mark_hub_invoice_paid(invoice_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from app.services.sales_hub_invoice_service import STATUS_PAID, SalesHubInvoiceService

    inv = SalesHubInvoiceService.get(db, invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    try:
        inv = SalesHubInvoiceService.set_status(db, inv=inv, status=STATUS_PAID)
    except SalesRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    items = SalesHubInvoiceService.list_items(db, inv.id)
    return {"ok": True, "invoice": SalesHubInvoiceService.invoice_to_dict(inv, items)}


@router.post("/hub-invoices/{invoice_id}/reject")
def reject_hub_invoice(
    invoice_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)
):
    from app.services.sales_hub_invoice_service import STATUS_REJECTED, SalesHubInvoiceService

    inv = SalesHubInvoiceService.get(db, invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    try:
        inv = SalesHubInvoiceService.set_status(
            db, inv=inv, status=STATUS_REJECTED, reason=(payload or {}).get("reason")
        )
    except SalesRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    items = SalesHubInvoiceService.list_items(db, inv.id)
    return {"ok": True, "invoice": SalesHubInvoiceService.invoice_to_dict(inv, items)}


@router.post("/hub-invoices/{invoice_id}/approve-commission")
def approve_hub_commission(
    invoice_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)
):
    from app.services.sales_hub_invoice_service import SalesHubInvoiceService

    inv = SalesHubInvoiceService.get(db, invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    approved = True if payload is None or "approved" not in payload else bool(payload.get("approved"))
    try:
        inv = SalesHubInvoiceService.approve_commission(db, inv=inv, approved=approved)
    except SalesRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    items = SalesHubInvoiceService.list_items(db, inv.id)
    return {"ok": True, "invoice": SalesHubInvoiceService.invoice_to_dict(inv, items)}


@router.post("/hub-invoices/{invoice_id}/collect")
def collect_hub_invoice(
    invoice_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)
):
    from app.services.sales_hub_invoice_service import SalesHubInvoiceService

    inv = SalesHubInvoiceService.get(db, invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    rep = db.get(SalesRep, inv.sales_rep_id)
    org = SalesRepService.partner_org_for_user(db, user_id=rep.user_id) if rep else None
    try:
        result = SalesHubInvoiceService.start_collect(
            db, inv=inv, provider=(payload or {}).get("provider"), org=org
        )
    except SalesRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result


@router.get("/team-kpis")
def sales_team_kpis(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from sqlalchemy import func, select

    from app.models.sales_rep import SalesCommission
    from app.services.sales_hub_invoice_service import SalesHubInvoiceService

    reps = SalesRepService.list_reps(db)
    leads = 0
    paying = 0
    revenue = 0
    for r in reps:
        paying += int(r.get("customers") or 0)
    # Real wallet totals from SalesCommission (pending + requested + paid)
    earned = int(
        db.execute(select(func.coalesce(func.sum(SalesCommission.amount_minor), 0))).scalar() or 0
    )
    paid = int(
        db.execute(
            select(func.coalesce(func.sum(SalesCommission.amount_minor), 0)).where(
                SalesCommission.status == "paid"
            )
        ).scalar()
        or 0
    )
    hub_kpis = SalesHubInvoiceService.kpi_totals(db)
    outstanding = int(hub_kpis.get("new") or 0) + int(hub_kpis.get("sent") or 0)
    salesmen = sum(1 for r in reps if r.get("kind") == "salesman")
    partners = sum(1 for r in reps if r.get("kind") == "partner_channel")
    return {
        "ok": True,
        "accounts": len(reps),
        "salesmen": salesmen,
        "partners": partners,
        "leads": leads,
        "paying_customers": paying,
        "revenue_minor": revenue,
        "commission_earned_minor": earned,
        "commission_paid_minor": paid,
        "invoices_outstanding_minor": outstanding,
        "hub_invoice_kpis": hub_kpis,
    }


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
    mailbox = body.get("mailbox") if isinstance(body.get("mailbox"), dict) else {
        k: body.get(k)
        for k in (
            "smtp_host",
            "smtp_port",
            "smtp_use_tls",
            "smtp_use_ssl",
            "smtp_username",
            "smtp_password",
            "imap_host",
            "imap_port",
            "imap_use_ssl",
            "imap_use_tls",
            "imap_username",
            "imap_password",
            "email_signature",
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
            promo_benefits=body.get("promo_benefits"),
            commission_tiers=body.get("commission_tiers"),
            partner_terms=body.get("partner_terms"),
            commission_mode=body.get("commission_mode"),
            one_time_bonus_minor=body.get("one_time_bonus_minor"),
            mailbox=mailbox or None,
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


@router.post("/{rep_id}/test-mailbox")
def test_sales_rep_mailbox(
    rep_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)
):
    """Test SMTP + IMAP connection. If username+password provided, test those; else test stored rep credentials."""
    body = payload or {}
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "").strip()

    if rep_id and rep_id != "test":
        rep = _get_rep(db, rep_id)
        if not username:
            username = rep.smtp_username or ""
        if not password:
            from app.core.security import decrypt_str
            password = decrypt_str(rep.smtp_password) if rep.smtp_password else ""
    
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    if not password:
        raise HTTPException(status_code=400, detail="Password is required for testing")

    smtp_ok = False
    imap_ok = False
    message = []

    # Test SMTP
    try:
        import smtplib
        from email.mime.text import MIMEText
        with smtplib.SMTP("mail.voxbulk.com", 587, timeout=10) as server:
            server.starttls()
            server.login(username, password)
            smtp_ok = True
            message.append("SMTP OK")
    except Exception as e:
        message.append(f"SMTP failed: {str(e)[:80]}")

    # Test IMAP
    try:
        import imaplib
        with imaplib.IMAP4_SSL("mail.voxbulk.com", 993, timeout=10) as mail:
            mail.login(username, password)
            imap_ok = True
            message.append("IMAP OK")
    except Exception as e:
        message.append(f"IMAP failed: {str(e)[:80]}")

    ok = smtp_ok and imap_ok
    return {"ok": ok, "smtp_ok": smtp_ok, "imap_ok": imap_ok, "message": " · ".join(message)}


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
