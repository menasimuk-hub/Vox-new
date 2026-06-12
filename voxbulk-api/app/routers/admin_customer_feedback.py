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
from app.models.customer_feedback import FeedbackIndustry, FeedbackPackage, FeedbackSurveyType, FeedbackWaTemplate
from app.models.organisation import Organisation
from sqlalchemy import select, func
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


@router.get("/industries/{industry_id}")
def get_industry(industry_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    try:
        return {"ok": True, "item": FeedbackCatalogService.get_industry_detail(db, industry_id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/industries/{industry_id}")
def delete_industry(industry_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.models.customer_feedback import FeedbackLocation

    row = db.get(FeedbackIndustry, industry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Industry not found")
    in_use = db.execute(
        select(func.count()).select_from(FeedbackLocation).where(FeedbackLocation.industry_id == industry_id)
    ).scalar_one()
    if int(in_use or 0) > 0:
        raise HTTPException(status_code=400, detail="Industry has active locations and cannot be deleted.")
    row.is_active = False
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    return {"ok": True}


@router.post("/industries/{industry_id}/sync-telnyx")
def sync_industry_templates(industry_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    rows = list(
        db.execute(
            select(FeedbackWaTemplate).where(FeedbackWaTemplate.industry_id == industry_id)
        ).scalars().all()
    )
    now = datetime.utcnow()
    for row in rows:
        row.telnyx_sync_status = "submitted"
        row.updated_at = now
        db.add(row)
    db.commit()
    return {"ok": True, "submitted": len(rows)}


@router.post("/templates/import-md")
def import_templates_md(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.customer_feedback.template_import_service import FeedbackTemplateImportService

    try:
        result = FeedbackTemplateImportService.import_from_md(
            db, replace_existing=bool(payload.get("replace_existing"))
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result


@router.get("/plans/pricing")
def list_pricing_rows(
    currency: str = Query("GBP"),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    from app.models.plan import Plan
    from app.models.plan_price import PlanPrice

    currency = str(currency or "GBP").upper()
    zone_map = {"GBP": "gb", "EUR": "eu", "USD": "us", "CAD": "ca", "AUD": "au"}
    zone = zone_map.get(currency, "gb")
    rows = list(
        db.execute(
            select(Plan, FeedbackPackage, PlanPrice)
            .join(FeedbackPackage, FeedbackPackage.plan_id == Plan.id)
            .join(PlanPrice, PlanPrice.plan_id == Plan.id)
            .where(Plan.service_kind == "customer_feedback", FeedbackPackage.market_zone == zone, PlanPrice.currency == currency)
            .order_by(FeedbackPackage.display_order, Plan.name)
        ).all()
    )
    items = []
    for plan, pkg, price in rows:
        items.append(
            {
                "plan_id": plan.id,
                "package_id": pkg.id,
                "name": plan.name,
                "code": plan.code,
                "price_minor": price.monthly_price_minor,
                "wa_units_included": pkg.wa_units_included,
                "max_locations": pkg.max_locations,
                "promo_message_cost_minor": pkg.promo_message_cost_minor,
                "is_frozen": bool(plan.is_frozen),
                "is_active": bool(plan.is_active and pkg.is_active),
                "currency": currency,
            }
        )
    return {"ok": True, "currency": currency, "items": items}


@router.put("/plans/pricing/bulk")
def save_pricing_rows(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.models.plan import Plan
    from app.models.plan_price import PlanPrice

    currency = str(payload.get("currency") or "GBP").upper()
    rows = payload.get("items") or []
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="items must be a list")
    now = datetime.utcnow()
    saved = 0
    for row in rows:
        plan = db.get(Plan, str(row.get("plan_id") or ""))
        if plan is None or bool(plan.is_frozen):
            continue
        pkg = db.execute(select(FeedbackPackage).where(FeedbackPackage.plan_id == plan.id)).scalar_one_or_none()
        if pkg is None:
            continue
        plan.name = str(row.get("name") or plan.name).strip()
        plan.is_active = bool(row.get("is_active", plan.is_active))
        if "is_frozen" in row:
            plan.is_frozen = bool(row.get("is_frozen"))
        plan.updated_at = now
        pkg.max_locations = int(row.get("max_locations") or pkg.max_locations or 1)
        pkg.wa_units_included = int(row.get("wa_units_included") or pkg.wa_units_included or 0)
        pkg.promo_message_cost_minor = int(row.get("promo_message_cost_minor") or pkg.promo_message_cost_minor or 5)
        pkg.updated_at = now
        price = db.execute(
            select(PlanPrice).where(PlanPrice.plan_id == plan.id, PlanPrice.currency == currency)
        ).scalar_one_or_none()
        if price is None:
            price = PlanPrice(id=str(uuid.uuid4()), plan_id=plan.id, currency=currency, created_at=now, updated_at=now)
            db.add(price)
        price.monthly_price_minor = int(row.get("price_minor") or price.monthly_price_minor or 0)
        price.updated_at = now
        db.add(plan)
        db.add(pkg)
        db.add(price)
        saved += 1
    db.commit()
    return {"ok": True, "saved": saved}


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


@router.get("/survey-types/{survey_type_id}")
def get_survey_type(survey_type_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    try:
        return {"ok": True, "item": FeedbackCatalogService.get_survey_type_detail(db, survey_type_id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/survey-types/{survey_type_id}/sync-telnyx")
def sync_survey_type_templates(
    survey_type_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))
):
    row = db.get(FeedbackSurveyType, survey_type_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Survey type not found")
    rows = list(
        db.execute(select(FeedbackWaTemplate).where(FeedbackWaTemplate.survey_type_id == survey_type_id)).scalars().all()
    )
    now = datetime.utcnow()
    for tpl in rows:
        tpl.telnyx_sync_status = "submitted"
        tpl.updated_at = now
        db.add(tpl)
    db.commit()
    return {"ok": True, "submitted": len(rows)}


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
    import json

    now = datetime.utcnow()
    row_id = str(payload.get("id") or "").strip()
    if row_id:
        row = db.get(FeedbackWaTemplate, row_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Template not found")
    else:
        row = FeedbackWaTemplate(id=str(uuid.uuid4()), created_at=now)
        db.add(row)
    row.industry_id = payload.get("industry_id") or row.industry_id or None
    row.survey_type_id = payload.get("survey_type_id") or row.survey_type_id or None
    row.step_order = int(payload.get("step_order") or row.step_order or 1)
    row.template_key = str(payload.get("template_key") or row.template_key or "question")
    row.body_text = str(payload.get("body_text") or row.body_text or "")
    if payload.get("step_role") is not None:
        row.step_role = str(payload.get("step_role") or "") or None
    if payload.get("language"):
        row.language = str(payload.get("language"))
    if payload.get("meta_category"):
        row.meta_category = str(payload.get("meta_category"))
    if "buttons" in payload:
        buttons = payload.get("buttons")
        row.buttons_json = json.dumps(buttons) if isinstance(buttons, list) else None
    if "is_active" in payload:
        row.is_active = bool(payload.get("is_active"))
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return {"ok": True, "item": FeedbackCatalogService.template_to_dict(row)}
