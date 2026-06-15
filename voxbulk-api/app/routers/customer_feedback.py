"""Customer dashboard API — Customer Feedback."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal, require_billing_access
from app.models.organisation import Organisation
from app.services.customer_feedback.billing_service import FeedbackBillingError, FeedbackBillingService
from app.services.customer_feedback.catalog_service import FeedbackCatalogService
from app.services.customer_feedback.location_service import FeedbackLocationService
from app.services.customer_feedback.results_service import FeedbackResultsService
from app.schemas.dashboard import SubscriptionCancellationOut, SubscriptionCancellationRequestIn
from app.services.gocardless_service import GoCardlessConfigError, GoCardlessProviderError
from app.services.org_enabled_services import is_service_enabled, org_service_maps

router = APIRouter(prefix="/customer-feedback", tags=["customer-feedback"])


def _require_feedback_enabled(db: Session, org_id: str) -> None:
    org = db.get(Organisation, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    _allowed, _enabled, visible = org_service_maps(org, db)
    if not is_service_enabled(visible, "customer_feedback"):
        raise HTTPException(status_code=403, detail="Customer feedback is not enabled for this organisation.")


@router.get("/catalog/industries")
def list_industries(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_feedback_enabled(db, principal.org_id)
    return {"ok": True, "items": FeedbackCatalogService.list_industries(db)}


@router.get("/catalog/survey-types")
def list_survey_types(
    industry_id: str | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    _require_feedback_enabled(db, principal.org_id)
    return {"ok": True, "items": FeedbackCatalogService.list_survey_types(db, industry_id=industry_id)}


@router.get("/subscription")
def get_subscription(db: Session = Depends(get_db), principal=Depends(require_billing_access)):
    _require_feedback_enabled(db, principal.org_id)
    return {"ok": True, **FeedbackBillingService.subscription_payload(db, principal.org_id)}


@router.get("/packages")
def list_packages(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_feedback_enabled(db, principal.org_id)
    org = db.get(Organisation, principal.org_id)
    return {"ok": True, "items": FeedbackBillingService.list_customer_packages(db, org)}


@router.post("/subscription/gocardless/start")
def start_gocardless(payload: dict, db: Session = Depends(get_db), principal=Depends(require_billing_access)):
    _require_feedback_enabled(db, principal.org_id)
    plan_id = str(payload.get("plan_id") or "").strip()
    if not plan_id:
        raise HTTPException(status_code=400, detail="plan_id required")
    try:
        res = FeedbackBillingService.start_gocardless_signup(
            db, org_id=principal.org_id, user_id=principal.user_id, plan_id=plan_id
        )
    except FeedbackBillingError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    plan = res["plan"]
    return {
        "ok": True,
        "redirect_flow_id": res["redirect_flow_id"],
        "authorization_url": res["authorization_url"],
        "plan_id": plan.id,
        "plan_name": plan.name,
    }


@router.post("/subscription/gocardless/complete")
def complete_gocardless(payload: dict, db: Session = Depends(get_db), principal=Depends(require_billing_access)):
    _require_feedback_enabled(db, principal.org_id)
    flow_id = str(payload.get("redirect_flow_id") or "").strip()
    if not flow_id:
        raise HTTPException(status_code=400, detail="redirect_flow_id required")
    try:
        res = FeedbackBillingService.complete_gocardless_signup(
            db, org_id=principal.org_id, user_id=principal.user_id, redirect_flow_id=flow_id
        )
    except FeedbackBillingError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "subscription": FeedbackBillingService.subscription_payload(db, principal.org_id)}


@router.post("/subscription/change-plan")
def change_feedback_plan(payload: dict, db: Session = Depends(get_db), principal=Depends(require_billing_access)):
    _require_feedback_enabled(db, principal.org_id)
    plan_id = str(payload.get("plan_id") or "").strip()
    if not plan_id:
        raise HTTPException(status_code=400, detail="plan_id required")
    try:
        result = FeedbackBillingService.change_plan(db, org_id=principal.org_id, plan_id=plan_id)
    except FeedbackBillingError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, **result, "subscription": FeedbackBillingService.subscription_payload(db, principal.org_id)}


@router.get("/subscription/cancellation", response_model=SubscriptionCancellationOut)
def get_feedback_cancellation(db: Session = Depends(get_db), principal=Depends(require_billing_access)):
    _require_feedback_enabled(db, principal.org_id)
    try:
        payload = FeedbackBillingService.cancellation_payload(db, principal.org_id)
    except FeedbackBillingError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return SubscriptionCancellationOut.model_validate(payload)


@router.post("/subscription/cancellation", response_model=SubscriptionCancellationOut)
def request_feedback_cancellation(
    payload: SubscriptionCancellationRequestIn,
    db: Session = Depends(get_db),
    principal=Depends(require_billing_access),
):
    _require_feedback_enabled(db, principal.org_id)
    try:
        result = FeedbackBillingService.request_cancellation(
            db,
            org_id=principal.org_id,
            user_id=principal.user_id,
            reason=payload.reason,
            requested_refund_type=payload.requested_refund_type,
        )
    except FeedbackBillingError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return SubscriptionCancellationOut.model_validate(result)


@router.post("/subscription/cancellation/reverse", response_model=SubscriptionCancellationOut)
def reverse_feedback_cancellation(db: Session = Depends(get_db), principal=Depends(require_billing_access)):
    _require_feedback_enabled(db, principal.org_id)
    try:
        result = FeedbackBillingService.reverse_cancellation(
            db, org_id=principal.org_id, user_id=principal.user_id
        )
    except FeedbackBillingError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return SubscriptionCancellationOut.model_validate(result)


@router.get("/locations")
def list_locations(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_feedback_enabled(db, principal.org_id)
    return {"ok": True, "items": FeedbackLocationService.list_locations(db, principal.org_id)}


@router.post("/locations/preview")
def preview_location(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_feedback_enabled(db, principal.org_id)
    try:
        item = FeedbackLocationService.preview_location(db, principal.org_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "item": item}


@router.post("/locations")
def create_location(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_feedback_enabled(db, principal.org_id)
    try:
        item = FeedbackLocationService.create_location(db, principal.org_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "item": item}


@router.patch("/locations/{location_id}")
def update_location(
    location_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    _require_feedback_enabled(db, principal.org_id)
    try:
        item = FeedbackLocationService.update_location(db, principal.org_id, location_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "item": item}


@router.delete("/locations/{location_id}")
def delete_location(
    location_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    _require_feedback_enabled(db, principal.org_id)
    try:
        FeedbackLocationService.delete_location(db, principal.org_id, location_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


@router.get("/results")
def get_results(
    location_id: str | None = None,
    survey_type_id: str | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    _require_feedback_enabled(db, principal.org_id)
    return FeedbackResultsService.customer_results(
        db, principal.org_id, location_id=location_id, survey_type_id=survey_type_id
    )
