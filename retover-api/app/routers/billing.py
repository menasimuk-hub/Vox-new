from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.models.plan import Plan
from app.schemas.dashboard import (
    BillingRedirectCompleteIn,
    BillingRedirectCompleteOut,
    BillingRedirectStartOut,
    CashPlanSelectIn,
    PlanOut,
    SubscriptionOut,
    SubscriptionWithPlanOut,
)
from app.services.gocardless_service import BillingService, GoCardlessConfigError, GoCardlessProviderError

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans", response_model=list[PlanOut])
def list_plans(db: Session = Depends(get_db)):
    return BillingService.list_plans(db)


@router.get("/subscription", response_model=SubscriptionWithPlanOut)
def get_my_subscription(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    BillingService.ensure_default_plans(db)
    sub = BillingService.get_subscription(db, principal.org_id)
    plan_row = None
    if sub:
        plan_row = db.execute(select(Plan).where(Plan.id == sub.plan_id)).scalar_one_or_none()
    return SubscriptionWithPlanOut(
        subscription=SubscriptionOut.model_validate(sub) if sub else None,
        plan=PlanOut.model_validate(plan_row) if plan_row else None,
        test_cash_billing_enabled=get_settings().test_cash_billing_allowed,
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

