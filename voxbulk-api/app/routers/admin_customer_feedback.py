"""Admin API — Customer Feedback service."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_INTEGRATION, require_cap
from app.core.database import get_db
from app.services.customer_feedback.billing_service import FeedbackBillingService
from app.services.customer_feedback.catalog_service import FeedbackCatalogService
from app.services.customer_feedback.location_service import FeedbackLocationService, location_to_dict
from app.services.customer_feedback.results_service import FeedbackResultsService
from app.models.customer_feedback import FeedbackWaTemplate
from app.models.organisation import Organisation
from sqlalchemy import select
import uuid
from datetime import datetime

router = APIRouter(prefix="/admin/customer-feedback", tags=["admin-customer-feedback"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    FeedbackCatalogService.ensure_ready(db)
    industries = FeedbackCatalogService.list_industries(db, include_inactive=True)
    packages = FeedbackCatalogService.list_packages(db, active_only=False)
    return {"ok": True, "industries": len(industries), "packages": len(packages)}


@router.get("/industries")
def list_industries(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    return {"ok": True, "items": FeedbackCatalogService.list_industries(db, include_inactive=True)}


@router.post("/industries")
def upsert_industry(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    try:
        return {"ok": True, "item": FeedbackCatalogService.upsert_industry(db, payload)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/survey-types")
def list_survey_types(
    industry_id: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return {
        "ok": True,
        "items": FeedbackCatalogService.list_survey_types(db, industry_id=industry_id, include_archived=True),
    }


@router.post("/survey-types")
def upsert_survey_type(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    try:
        return {"ok": True, "item": FeedbackCatalogService.upsert_survey_type(db, payload)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/plans")
def list_feedback_plans(
    market_zone: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return {"ok": True, "items": FeedbackCatalogService.list_feedback_plans(db, market_zone=market_zone)}


@router.get("/packages")
def list_packages(
    market_zone: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return {"ok": True, "items": FeedbackCatalogService.list_packages(db, market_zone=market_zone, active_only=False)}


@router.post("/packages")
def upsert_package(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    try:
        return {"ok": True, "item": FeedbackCatalogService.upsert_package(db, payload)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/subscriptions")
def list_subscriptions(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.models.subscription import Subscription
    from app.models.plan import Plan

    rows = list(
        db.execute(
            select(Subscription, Organisation, Plan)
            .join(Organisation, Organisation.id == Subscription.org_id)
            .join(Plan, Plan.id == Subscription.plan_id)
            .where(Subscription.service_code == "customer_feedback")
            .order_by(Subscription.updated_at.desc())
            .limit(200)
        ).all()
    )
    items = []
    for sub, org, plan in rows:
        usage = FeedbackBillingService.get_current_usage(db, org.id)
        items.append(
            {
                "org_id": org.id,
                "org_name": org.name,
                "status": sub.status,
                "plan_name": plan.name,
                **usage,
            }
        )
    return {"ok": True, "items": items}


@router.get("/locations")
def admin_list_locations(
    org_id: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    from app.models.customer_feedback import FeedbackLocation

    q = select(FeedbackLocation).order_by(FeedbackLocation.created_at.desc()).limit(500)
    if org_id:
        q = q.where(FeedbackLocation.org_id == org_id)
    rows = list(db.execute(q).scalars().all())
    return {"ok": True, "items": [location_to_dict(db, row) for row in rows]}


@router.get("/results")
def admin_results(
    org_id: str | None = None,
    location_id: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return FeedbackResultsService.admin_results(db, org_id=org_id, location_id=location_id)


@router.get("/wa-templates")
def list_wa_templates(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    rows = list(db.execute(select(FeedbackWaTemplate).order_by(FeedbackWaTemplate.step_order)).scalars().all())
    return {
        "ok": True,
        "items": [
            {
                "id": r.id,
                "industry_id": r.industry_id,
                "survey_type_id": r.survey_type_id,
                "step_order": r.step_order,
                "template_key": r.template_key,
                "body_text": r.body_text,
                "is_active": r.is_active,
            }
            for r in rows
        ],
    }


@router.post("/wa-templates")
def upsert_wa_template(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    now = datetime.utcnow()
    row_id = str(payload.get("id") or "").strip()
    if row_id:
        row = db.get(FeedbackWaTemplate, row_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Template not found")
    else:
        row = FeedbackWaTemplate(id=str(uuid.uuid4()), created_at=now)
        db.add(row)
    row.industry_id = payload.get("industry_id") or None
    row.survey_type_id = payload.get("survey_type_id") or None
    row.step_order = int(payload.get("step_order") or row.step_order or 1)
    row.template_key = str(payload.get("template_key") or row.template_key or "question")
    row.body_text = str(payload.get("body_text") or row.body_text or "")
    row.is_active = bool(payload.get("is_active", row.is_active if row_id else True))
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return {"ok": True, "id": row.id}
