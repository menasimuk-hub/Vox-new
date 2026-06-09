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
    currency: str = "auto",
    market: str = "auto",
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.models.organisation import Organisation
    from app.services.billing_currency import SUPPORTED_CURRENCIES, resolve_org_currency
    from app.services.voxbulk_pricing_service import VoxbulkPricingService

    VoxbulkPricingService.ensure_seeded(db)
    org_id = principal.org_id if principal else None
    org = db.get(Organisation, org_id) if org_id else None
    requested = str(currency if currency != "auto" else market).strip().upper()
    resolved = requested if requested in SUPPORTED_CURRENCIES else resolve_org_currency(db, org)
    payload = VoxbulkPricingService.public_pricing_payload(db, currency=resolved, org_id=org_id)
    payload["org_country"] = str(org.country or "").strip() if org else None
    payload["org_currency"] = resolved
    payload["org_market"] = resolved.lower()
    return payload


@router.get("/pricing/public")
def get_public_pricing_anonymous(currency: str = "GBP", market: str = "", db: Session = Depends(get_db)):
    from app.services.voxbulk_pricing_service import VoxbulkPricingService

    VoxbulkPricingService.ensure_seeded(db)
    resolved = str(market or currency or "GBP").strip().upper() or "GBP"
    return VoxbulkPricingService.public_pricing_payload(db, currency=resolved, org_id=None)


@router.get("/wallet")
def get_wallet(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.models.organisation import Organisation
    from app.services.wallet_service import WalletService

    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    return WalletService.wallet_dict(db, org)


@router.get("/wallet/transactions")
def list_wallet_transactions(
    limit: int = 100,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.wallet_service import WalletService

    rows = WalletService.list_transactions(db, principal.org_id, limit=limit)
    return {"ok": True, "transactions": [WalletService.transaction_to_dict(r) for r in rows]}


@router.get("/wallet/topup/options")
def wallet_topup_options(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    """Enabled card processors and suggested top-up amounts for the org currency."""
    from app.models.organisation import Organisation
    from app.services.airwallex_payment_service import AirwallexPaymentService
    from app.services.billing_currency import money_display, resolve_org_currency
    from app.services.stripe_payment_service import StripePaymentService
    from app.services.voxbulk_pricing_service import VoxbulkPricingService
    from app.services.wallet_service import WalletService

    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    currency = resolve_org_currency(db, org)
    providers = []
    if StripePaymentService.is_available(db):
        providers.append({"id": "stripe", "label": "Card (Stripe)", "publishable_key": StripePaymentService.publishable_key(db)})
    if AirwallexPaymentService.is_available(db):
        providers.append({"id": "airwallex", "label": "Card (Airwallex)"})
    tiers = [
        VoxbulkPricingService.topup_tier_to_dict(t, currency=currency)
        for t in VoxbulkPricingService.list_topup_tiers(db, active_only=True)
    ]
    return {
        "ok": True,
        "currency": currency,
        "providers": providers,
        "suggested_amounts": tiers,
        "min_amount_minor": WalletService.MIN_TOPUP_MINOR,
        "min_amount_display": money_display(WalletService.MIN_TOPUP_MINOR, currency),
        **WalletService.wallet_dict(db, org),
    }


@router.post("/wallet/topup/intent")
def wallet_topup_intent(
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    """Create a Stripe/Airwallex PaymentIntent for a wallet top-up."""
    from app.models.organisation import Organisation
    from app.services.airwallex_payment_service import (
        AirwallexConfigError,
        AirwallexPaymentService,
        AirwallexProviderError,
    )
    from app.services.stripe_payment_service import (
        StripeConfigError,
        StripePaymentService,
        StripeProviderError,
    )
    from app.services.wallet_service import WalletService

    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    provider = str(payload.get("provider") or "").strip().lower()
    amount = int(payload.get("amount_minor") or payload.get("amount_pence") or 0)
    if amount < WalletService.MIN_TOPUP_MINOR:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Minimum top-up is 5.00")
    if amount > 1_000_000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Maximum top-up is 10,000.00")
    try:
        if provider == "stripe":
            return {"ok": True, **StripePaymentService.create_topup_intent(db, org, amount_minor=amount)}
        if provider == "airwallex":
            return {"ok": True, **AirwallexPaymentService.create_topup_intent(db, org, amount_minor=amount)}
    except (StripeConfigError, AirwallexConfigError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except (StripeProviderError, AirwallexProviderError) as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="provider must be stripe or airwallex")


@router.post("/wallet/topup/confirm")
def wallet_topup_confirm(
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    """Server-side verification of a completed top-up payment; credits the wallet once."""
    from app.models.organisation import Organisation
    from app.services.airwallex_payment_service import (
        AirwallexConfigError,
        AirwallexPaymentService,
        AirwallexProviderError,
    )
    from app.services.stripe_payment_service import (
        StripeConfigError,
        StripePaymentService,
        StripeProviderError,
    )
    from app.services.wallet_service import WalletService

    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    provider = str(payload.get("provider") or "").strip().lower()
    intent_id = str(payload.get("payment_intent_id") or "").strip()
    try:
        if provider == "stripe":
            result = StripePaymentService.confirm_topup(db, org, payment_intent_id=intent_id)
        elif provider == "airwallex":
            result = AirwallexPaymentService.confirm_topup(db, org, payment_intent_id=intent_id)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="provider must be stripe or airwallex")
    except (StripeConfigError, AirwallexConfigError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except (StripeProviderError, AirwallexProviderError) as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    db.refresh(org)
    return {**result, **WalletService.wallet_dict(db, org)}


@router.post("/wallet/topup")
def wallet_topup_test_cash(
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    """Dev/testing only: credit the wallet without a card payment."""
    from app.models.organisation import Organisation
    from app.services.wallet_service import WalletError, WalletService

    settings = get_settings()
    if not settings.test_cash_billing_allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use /billing/wallet/topup/intent with Stripe or Airwallex to top up.",
        )
    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    amount = int(payload.get("amount_minor") or payload.get("amount_pence") or 0)
    tier_id = str(payload.get("tier_id") or "").strip() or None
    if tier_id:
        tier = db.get(TopupTier, tier_id)
        if tier is None or not tier.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid top-up tier")
        amount = int(tier.credit_gbp_pence or 0) + int(tier.bonus_credit_pence or 0)
    if amount < WalletService.MIN_TOPUP_MINOR:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Minimum top-up is 5.00")
    try:
        WalletService.credit(
            db,
            org,
            amount_minor=amount,
            kind="topup",
            provider="manual",
            description="Test cash top-up (dev)",
            created_by_user_id=principal.user_id,
        )
    except WalletError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    db.refresh(org)
    return {"ok": True, "credited_pence": amount, **WalletService.wallet_dict(db, org)}


@router.get("/payment-options", response_model=PaymentOptionsOut)
def get_payment_options(db: Session = Depends(get_db)):
    return PaymentOptionsOut.model_validate(BillingService.payment_options(db))


@router.post("/subscription/pay-as-you-go")
def switch_subscription_to_pay_as_you_go(
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    """Switch to the zero-fee pay-as-you-go plan (wallet top-ups only)."""
    try:
        sub, plan = BillingService.switch_to_pay_as_you_go(db, org_id=principal.org_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    UsageWalletService.sync_plan_limits(db, org_id=principal.org_id, plan=plan, subscription=sub)
    return {
        "ok": True,
        "subscription": SubscriptionOut.model_validate(sub),
        "plan": PlanOut.model_validate(plan),
    }


@router.post("/subscription/change-plan")
def change_subscription_plan(
    payload: CashPlanSelectIn,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    """Request a plan change via cash/testing — awaits admin approval before activation."""
    try:
        from app.services.billing_lifecycle_service import BillingLifecycleService

        sub, plan, direction, extra = BillingLifecycleService.change_subscription_plan(
            db,
            org_id=principal.org_id,
            plan_id=(payload.plan_id or "").strip() or None,
            plan_code=(payload.plan_code or "").strip() or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    awaiting_admin = sub.status == "pending_payment" and sub.payment_provider == "manual_cash"
    if sub and not awaiting_admin and direction in {"upgrade", "same"}:
        UsageWalletService.sync_plan_limits(db, org_id=principal.org_id, plan=plan, subscription=sub)

    return {
        "ok": True,
        "direction": direction,
        "awaiting_admin_approval": awaiting_admin,
        "subscription": SubscriptionOut.model_validate(sub),
        "plan": PlanOut.model_validate(plan),
        "pending_plan": PlanOut.model_validate(plan) if awaiting_admin or direction == "downgrade" else None,
        "billing": extra,
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

    row = (
        db.execute(
            select(BillingRedirectFlow)
            .where(BillingRedirectFlow.session_token == token)
            .order_by(BillingRedirectFlow.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    origin = BillingService._resolved_dashboard_origin()
    billing_state = str(billing or "success").strip().lower()
    if billing_state not in {"success", "cancelled"}:
        billing_state = "success"

    if row is None:
        query = urlencode({"billing": "error"})
        return RedirectResponse(url=BillingService._dashboard_packages_url(origin, query=query), status_code=302)

    params = {"billing": billing_state}
    if billing_state == "success":
        params["redirect_flow_id"] = row.redirect_flow_id
    query = urlencode(params)
    return RedirectResponse(url=BillingService._dashboard_packages_url(origin, query=query), status_code=302)


@router.get("/usage-summary")
def get_usage_summary(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.models.organisation import Organisation
    from app.services.org_service_credit_service import OrgServiceCreditService

    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")

    row = UsageWalletService.get_current(db, principal.org_id)
    if row is None:
        sub = BillingService.get_subscription(db, principal.org_id)
        if sub is not None:
            try:
                row = UsageWalletService.bootstrap_from_plan(db, org_id=principal.org_id, subscription=sub)
            except Exception:
                row = None

    current_plan = BillingService.resolve_active_plan(db, principal.org_id)
    sub = BillingService.get_subscription(db, principal.org_id)

    usage_payload = UsageWalletService.summary_dict(row) if row else None
    pending_overage_pence = 0
    if row is not None:
        total_overage = UsageWalletService._calc_overage_pence(row, db, principal.org_id)
        pending_overage_pence = max(0, total_overage - int(row.overage_invoiced_pence or 0))
        billing_email = UsageWalletService.get_org_billing_email(db, principal.org_id)
        if billing_email and pending_overage_pence >= 100:
            try:
                UsageWalletService.maybe_invoice_overage(
                    db,
                    org_id=principal.org_id,
                    client_email=billing_email,
                    row=row,
                )
                row = UsageWalletService.get_current(db, principal.org_id)
                if row is not None:
                    usage_payload = UsageWalletService.summary_dict(row)
                    total_overage = UsageWalletService._calc_overage_pence(row, db, principal.org_id)
                    pending_overage_pence = max(0, total_overage - int(row.overage_invoiced_pence or 0))
            except Exception:
                pass

    cv_included = int(getattr(current_plan, "cv_scans_included", 0) or 0) if current_plan else 0
    cv_used = 0
    if row is not None:
        cv_used = int(getattr(row, "cv_scans_used", 0) or 0)
    wallet_pence = int(org.wallet_balance_pence or 0)
    promo = OrgServiceCreditService.balances_dict(org)

    def _meter(key: str, label: str, used: int, included: int, *, unit: str = "") -> dict:
        pct = round((used / included) * 100, 1) if included > 0 else 0.0
        remaining = max(0, included - used) if included > 0 else None
        return {
            "key": key,
            "label": label,
            "used": used,
            "included": included,
            "remaining": remaining,
            "percent": pct,
            "unit": unit,
            "unlimited": included <= 0,
        }

    calls = (usage_payload or {}).get("calls") or {}
    whatsapp = (usage_payload or {}).get("whatsapp") or {}
    sms = (usage_payload or {}).get("sms") or {}
    pack = (usage_payload or {}).get("pack_credits") or {}

    meters = [
        _meter("calls", "AI call minutes", int(calls.get("used") or 0), int(calls.get("included") or 0), unit="min"),
        _meter("whatsapp", "WA survey recipients", int(whatsapp.get("used") or 0), int(whatsapp.get("included") or 0), unit="recipients"),
        _meter("sms", "SMS messages", int(sms.get("used") or 0), int(sms.get("included") or 0)),
        _meter("cv_scans", "CV scans (ATS)", cv_used, cv_included),
        _meter(
            "pack_credits",
            "Promo pack credits",
            int(pack.get("used") or 0),
            int(pack.get("included") or 0),
        ),
        {
            "key": "wallet",
            "label": "Wallet balance",
            "used": wallet_pence,
            "included": 0,
            "remaining": wallet_pence,
            "percent": 0.0,
            "unit": "gbp",
            "unlimited": True,
            "display_gbp": f"£{wallet_pence / 100:.2f}",
        },
        {
            "key": "interview_credits",
            "label": "Interview promo credits",
            "used": 0,
            "included": int(promo.get("interview_credits") or 0),
            "remaining": int(promo.get("interview_credits") or 0),
            "percent": 0.0,
            "unit": "credits",
            "unlimited": False,
        },
        {
            "key": "survey_credits",
            "label": "Survey promo credits",
            "used": 0,
            "included": int(promo.get("survey_credits") or 0),
            "remaining": int(promo.get("survey_credits") or 0),
            "percent": 0.0,
            "unit": "credits",
            "unlimited": False,
        },
    ]

    return {
        "ok": True,
        "usage": usage_payload,
        "meters": meters,
        "wallet_balance_pence": wallet_pence,
        "wallet_balance_gbp": f"£{wallet_pence / 100:.2f}",
        "promo_credits": promo,
        "overage_pending_pence": pending_overage_pence,
        "overage_pending_gbp": f"£{pending_overage_pence / 100:.2f}",
        "estimated_overage_gbp": (usage_payload or {}).get("estimated_overage_gbp"),
        "period_start": (usage_payload or {}).get("period_start"),
        "period_end": (usage_payload or {}).get("period_end"),
        "current_plan": PlanOut.model_validate(current_plan) if current_plan else None,
        "subscription": SubscriptionOut.model_validate(sub) if sub else None,
    }


@router.get("/access")
def get_billing_access(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.models.organisation import Organisation
    from app.services.billing_access_service import BillingAccessService

    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    return BillingAccessService.access_summary(db, org)


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

