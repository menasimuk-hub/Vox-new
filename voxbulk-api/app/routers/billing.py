from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.models.billing_redirect_flow import BillingRedirectFlow
from app.models.plan import Plan
from app.models.pricing import TopupTier
from app.schemas.dashboard import (
    BillingRedirectCompleteIn,
    BillingRedirectCompleteOut,
    BillingRedirectStartOut,
    CashPlanSelectIn,
    PaymentOptionsOut,
    PlanOut,
    SubscriptionOut,
    SubscriptionWithPlanOut,
)
from app.services.gocardless_service import BillingService, GoCardlessConfigError, GoCardlessProviderError
from app.services.provider_settings import ProviderSettingsService
from app.services.usage_wallet_service import UsageWalletService

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans", response_model=list[PlanOut])
def list_plans(db: Session = Depends(get_db)):
    from app.services.voxbulk_pricing_service import VoxbulkPricingService

    VoxbulkPricingService.ensure_seeded(db)
    rows = BillingService.list_plans(db, active_only=True)
    voxbulk = [p for p in rows if getattr(p, "service_kind", "") == "voxbulk"]
    return voxbulk or rows


@router.get("/pricing")
def get_public_pricing(
    market: str = "auto",
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.models.organisation import Organisation
    from app.services.pricing_market_service import PricingMarketService
    from app.services.voxbulk_pricing_service import VoxbulkPricingService

    VoxbulkPricingService.ensure_seeded(db)
    org_id = principal.org_id if principal else None
    org = db.get(Organisation, org_id) if org_id else None
    resolved = PricingMarketService.resolve_market_param(db, org=org, market=market)
    payload = VoxbulkPricingService.public_pricing_payload(db, market=resolved, org_id=org_id)
    payload["org_country"] = str(org.country or "").strip() if org else None
    payload["org_market"] = resolved
    payload["market_label"] = PricingMarketService.market_label(resolved)
    return payload


@router.get("/pricing/public")
def get_public_pricing_anonymous(market: str = "gbp", db: Session = Depends(get_db)):
    from app.services.voxbulk_pricing_service import VoxbulkPricingService

    VoxbulkPricingService.ensure_seeded(db)
    return VoxbulkPricingService.public_pricing_payload(db, market=market, org_id=None)


@router.get("/wallet")
def get_wallet(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.models.organisation import Organisation

    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    return {
        "wallet_balance_pence": int(org.wallet_balance_pence or 0),
        "wallet_balance_gbp": f"£{(int(org.wallet_balance_pence or 0) / 100):.2f}",
    }


@router.post("/wallet/topup")
def wallet_topup(
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.models.organisation import Organisation
    from app.services.voxbulk_pricing_service import VoxbulkPricingService

    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    amount = int(payload.get("amount_pence") or 0)
    tier_id = str(payload.get("tier_id") or "").strip() or None
    if tier_id:
        tier = db.get(TopupTier, tier_id)
        if tier is None or not tier.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid top-up tier")
        amount = int(tier.credit_gbp_pence or 0) + int(tier.bonus_credit_pence or 0)
    if amount < 500:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Minimum top-up is £5.00")
    settings = get_settings()
    if not settings.test_cash_billing_allowed and not payload.get("payment_confirmed"):
        return {
            "ok": False,
            "awaiting_payment": True,
            "amount_pence": amount,
            "message": "Payment integration required — use test cash billing in dev or confirm payment.",
        }
    org = VoxbulkPricingService.deposit_wallet(db, org, amount)
    return {
        "ok": True,
        "wallet_balance_pence": int(org.wallet_balance_pence or 0),
        "wallet_balance_gbp": f"£{(int(org.wallet_balance_pence or 0) / 100):.2f}",
        "credited_pence": amount,
    }


@router.get("/payment-options", response_model=PaymentOptionsOut)
def get_payment_options(db: Session = Depends(get_db)):
    return PaymentOptionsOut.model_validate(BillingService.payment_options(db))


@router.post("/subscription/change-plan")
def change_subscription_plan(
    payload: CashPlanSelectIn,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    """Request a plan change via cash/testing — awaits admin approval before activation."""
    try:
        sub, plan, direction = BillingService.change_plan(
            db,
            org_id=principal.org_id,
            plan_id=(payload.plan_id or "").strip() or None,
            plan_code=(payload.plan_code or "").strip() or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return {
        "ok": True,
        "direction": direction,
        "awaiting_admin_approval": True,
        "subscription": SubscriptionOut.model_validate(sub),
        "plan": PlanOut.model_validate(plan),
        "pending_plan": PlanOut.model_validate(plan),
    }


@router.get("/subscription", response_model=SubscriptionWithPlanOut)
def get_my_subscription(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    BillingService.ensure_default_plans(db)
    sub = BillingService.repair_subscription_plan_id(db, principal.org_id)
    if sub is None:
        sub = BillingService.get_subscription(db, principal.org_id)
    resolved_plan = BillingService.resolve_active_plan(db, principal.org_id)
    gc_cfg, gc_enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="gocardless")
    gocardless_checkout_available = bool(gc_enabled and str(gc_cfg.get("access_token") or "").strip())
    pending_plan_row = None
    if sub and getattr(sub, "pending_plan_id", None):
        pending_plan_row = db.execute(select(Plan).where(Plan.id == sub.pending_plan_id)).scalar_one_or_none()
    active_plan_row = resolved_plan
    if sub and sub.status == "pending_payment" and sub.pending_plan_id and pending_plan_row:
        active_plan_row = resolved_plan or pending_plan_row
    return SubscriptionWithPlanOut(
        subscription=SubscriptionOut.model_validate(sub) if sub else None,
        plan=PlanOut.model_validate(active_plan_row) if active_plan_row else None,
        pending_plan=PlanOut.model_validate(pending_plan_row) if pending_plan_row else None,
        test_cash_billing_enabled=get_settings().test_cash_billing_allowed,
        gocardless_checkout_available=gocardless_checkout_available,
        payment_options=BillingService.payment_options(db),
    )


@router.post("/subscription/test-cash")
def test_cash_subscription_change(
    payload: CashPlanSelectIn,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    """
    Dev/testing only: record subscription change as paid (cash/manual) and auto-approve it.
    """
    if not get_settings().test_cash_billing_allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Test cash billing is disabled")
    try:
        sub = BillingService.assign_plan_cash(
            db,
            org_id=principal.org_id,
            plan_id=(payload.plan_id or "").strip() or None,
            plan_code=(payload.plan_code or "").strip() or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    plan_row = db.execute(select(Plan).where(Plan.id == sub.plan_id)).scalar_one_or_none()
    return {
        "ok": True,
        "subscription": SubscriptionOut.model_validate(sub),
        "plan": PlanOut.model_validate(plan_row) if plan_row else None,
        "test_cash_billing": True,
    }


@router.post("/subscription/cash")
def legacy_cash_subscription_change(
    payload: CashPlanSelectIn,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    """Backward-compatible alias for local tools. Still blocked unless test cash billing is enabled."""
    return test_cash_subscription_change(payload=payload, db=db, principal=principal)


@router.post("/subscription/gocardless/start", response_model=BillingRedirectStartOut)
def start_gocardless_checkout(
    payload: CashPlanSelectIn,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    """
    Start a sandbox/live GoCardless hosted redirect flow for the selected package.
    """
    try:
        res = BillingService.start_gocardless_redirect_flow(
            db,
            org_id=principal.org_id,
            user_id=principal.user_id,
            plan_id=(payload.plan_id or "").strip() or None,
            plan_code=(payload.plan_code or "").strip() or None,
        )
        return BillingRedirectStartOut(
            ok=True,
            environment=str(res["environment"]),
            redirect_flow_id=str(res["redirect_flow_id"]),
            authorization_url=str(res["authorization_url"]),
            cancel_url=str(res.get("cancel_url") or ""),
            plan=PlanOut.model_validate(res["plan"]),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except GoCardlessConfigError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except GoCardlessProviderError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e


@router.post("/subscription/gocardless/complete", response_model=BillingRedirectCompleteOut)
def complete_gocardless_checkout(
    payload: BillingRedirectCompleteIn,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    """Complete the GoCardless redirect flow and create the provider subscription."""
    try:
        res = BillingService.complete_gocardless_redirect_flow(
            db,
            org_id=principal.org_id,
            user_id=principal.user_id,
            redirect_flow_id=payload.redirect_flow_id,
        )
        sub = res.get("subscription")
        plan = res.get("plan")
        if sub is not None and plan is not None:
            UsageWalletService.sync_plan_limits(db, org_id=principal.org_id, plan=plan, subscription=sub)
        return BillingRedirectCompleteOut(
            ok=True,
            status=str(res["status"]),
            subscription=SubscriptionOut.model_validate(res["subscription"]) if res.get("subscription") else None,
            plan=PlanOut.model_validate(res["plan"]) if res.get("plan") else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except GoCardlessConfigError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except GoCardlessProviderError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e


@router.get("/subscription/gocardless/browser-return")
def gocardless_browser_return(
    session_token: str,
    billing: str = "success",
    db: Session = Depends(get_db),
):
    """
    GoCardless success/cancel hop: resolve session_token → redirect_flow_id, then send the
    browser to the dashboard with billing query params (works in fresh tabs).
    """
    token = str(session_token or "").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="session_token required")

    row = db.execute(
        select(BillingRedirectFlow).where(BillingRedirectFlow.session_token == token)
    ).scalar_one_or_none()
    origin = BillingService._resolved_dashboard_origin()
    billing_state = str(billing or "success").strip().lower()
    if billing_state not in {"success", "cancelled"}:
        billing_state = "success"

    if row is None:
        query = urlencode({"billing": "error"})
        return RedirectResponse(url=f"{origin}/packages?{query}", status_code=302)

    params = {"billing": billing_state}
    if billing_state == "success":
        params["redirect_flow_id"] = row.redirect_flow_id
    query = urlencode(params)
    return RedirectResponse(url=f"{origin}/packages?{query}", status_code=302)


@router.get("/usage-summary")
def get_usage_summary(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    row = UsageWalletService.get_current(db, principal.org_id)
    if row is None:
        sub = BillingService.get_subscription(db, principal.org_id)
        if sub is not None:
            try:
                row = UsageWalletService.bootstrap_from_plan(db, org_id=principal.org_id, subscription=sub)
            except Exception:
                row = None
    current_plan = BillingService.resolve_active_plan(db, principal.org_id)
    if row is None:
        return {
            "ok": True,
            "usage": None,
            "current_plan": PlanOut.model_validate(current_plan) if current_plan else None,
        }
    return {
        "ok": True,
        "usage": UsageWalletService.summary_dict(row),
        "current_plan": PlanOut.model_validate(current_plan) if current_plan else None,
    }


@router.get("/invoices")
def list_my_invoices(
    limit: int = 50,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.invoice_service import InvoiceService

    rows = InvoiceService.list_for_org(db, org_id=principal.org_id, limit=limit)
    return [InvoiceService.invoice_to_dict(db, r) for r in rows]


@router.get("/invoices/{invoice_id}")
def get_my_invoice(
    invoice_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.invoice_service import InvoiceService

    row = InvoiceService.get_for_org(db, invoice_id=invoice_id, org_id=principal.org_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return InvoiceService.invoice_to_dict(db, row)


@router.get("/invoices/{invoice_id}/html")
def get_my_invoice_html(
    invoice_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from fastapi.responses import HTMLResponse

    from app.services.invoice_service import InvoiceDocumentService
    from app.services.invoice_service import InvoiceService

    row = InvoiceService.get_for_org(db, invoice_id=invoice_id, org_id=principal.org_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return HTMLResponse(InvoiceDocumentService.render_html(db, invoice=row))


@router.get("/invoices/{invoice_id}/pdf")
def get_my_invoice_pdf(
    invoice_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from fastapi.responses import Response

    from app.services.invoice_service import InvoiceDocumentService
    from app.services.invoice_service import InvoiceService

    row = InvoiceService.get_for_org(db, invoice_id=invoice_id, org_id=principal.org_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    try:
        pdf_bytes = InvoiceDocumentService.render_pdf(db, invoice=row)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
    number = row.invoice_number or row.id
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="invoice-{number}.pdf"'},
    )

