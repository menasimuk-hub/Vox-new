"""Admin API — Customer Feedback service."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_INTEGRATION, require_cap
from app.core.database import get_db
from app.services.customer_feedback.billing_service import FeedbackBillingService
from app.services.customer_feedback.catalog_service import FeedbackCatalogService
from app.services.customer_feedback.location_service import FeedbackLocationService, location_to_dict
from app.services.customer_feedback.results_service import FeedbackResultsService
from app.models.customer_feedback import FeedbackIndustry, FeedbackPackage, FeedbackSurveyType, FeedbackWaSender, FeedbackWaTemplate
from app.models.organisation import Organisation
from sqlalchemy import select, func
import uuid
from datetime import datetime

router = APIRouter(prefix="/admin/customer-feedback", tags=["admin-customer-feedback"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    FeedbackCatalogService.ensure_ready(db)
    industries = FeedbackCatalogService.list_industries(db, include_inactive=False)
    packages = FeedbackCatalogService.list_packages(db, active_only=False)
    return {"ok": True, "industries": len(industries), "packages": len(packages)}


@router.get("/industries")
def list_industries(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    return {
        "ok": True,
        "items": FeedbackCatalogService.list_industries(db, include_inactive=False, include_org_ids=True),
    }


@router.get("/industries/{industry_id}")
def get_industry(industry_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    try:
        return {"ok": True, "item": FeedbackCatalogService.get_industry_detail(db, industry_id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/industries/{industry_id}/templates")
def list_industry_templates(
    industry_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    try:
        return {"ok": True, **FeedbackCatalogService.list_industry_hub_templates(db, industry_id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/industries/{industry_id}")
def update_industry(industry_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    body = dict(payload or {})
    body["id"] = industry_id
    try:
        return {"ok": True, "item": FeedbackCatalogService.upsert_industry(db, body)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/industries/{industry_id}")
def delete_industry(industry_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    try:
        return FeedbackCatalogService.delete_industry(db, industry_id)
    except ValueError as e:
        detail = str(e)
        code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=code, detail=detail) from e


@router.post("/industries/{industry_id}/sync-telnyx")
def sync_industry_templates(
    industry_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    from app.services.customer_feedback.feedback_telnyx_push_service import (
        FeedbackTelnyxPushError,
        push_feedback_templates_batch,
    )

    body = payload or {}
    phase = str(body.get("phase") or "push").strip().lower()
    try:
        summary = push_feedback_templates_batch(
            db,
            industry_id=industry_id,
            offset=int(body.get("offset") or 0),
            limit=int(body.get("limit") or 10),
            dry_run=bool(body.get("dry_run")),
            phase=phase,
        )
    except FeedbackTelnyxPushError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if phase == "pull":
        return {"ok": True, "phase": "pull", "pull": summary.get("pull"), "message": summary.get("message"), **summary}

    push_summary = summary
    failed = int(push_summary.get("failed") or 0)
    return {
        "ok": push_summary.get("ok", True) and failed == 0,
        "phase": "push",
        "message": push_summary.get("message"),
        "push": push_summary,
        "total": push_summary.get("total"),
        "processed": push_summary.get("processed"),
        "has_more": push_summary.get("has_more"),
        "next_offset": push_summary.get("next_offset"),
        "pushed": push_summary.get("pushed"),
        "linked": push_summary.get("linked"),
        "failed": failed,
        "errors": push_summary.get("errors"),
        "results": push_summary.get("results"),
        "content_updated": push_summary.get("content_updated"),
        "error_count": push_summary.get("error_count"),
    }


@router.post("/industries/{industry_id}/import-md")
async def import_industry_md(
    industry_id: str,
    file: UploadFile = File(...),
    dry_run: bool = Form(False),
    replace: bool = Form(True),
    create_missing: bool = Form(True),
    min_langs: int = Form(19),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    from app.services.customer_feedback.feedback_md_import_service import (
        FeedbackMdImportError,
        FeedbackMdImportService,
    )

    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="File must be UTF-8 text") from exc

    try:
        result = FeedbackMdImportService.import_from_text(
            db,
            text,
            industry_id=industry_id,
            replace=replace,
            create_missing_topics=create_missing,
            dry_run=dry_run,
            min_langs=min_langs,
            source_name=file.filename or "upload.md",
        )
    except FeedbackMdImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


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
                "web_units_included": pkg.web_units_included,
                "max_locations": pkg.max_locations,
                "promo_message_cost_minor": pkg.promo_message_cost_minor,
                "yearly_price_minor": price.yearly_price_minor,
                "is_frozen": bool(plan.is_frozen),
                "is_active": bool(plan.is_active and pkg.is_active),
                "currency": currency,
            }
        )
    return {"ok": True, "currency": currency, "items": items}


def _pricing_row_dict(plan, pkg, price, currency: str) -> dict[str, Any]:
    return {
        "plan_id": plan.id,
        "package_id": pkg.id,
        "name": plan.name,
        "code": plan.code,
        "price_minor": price.monthly_price_minor,
        "wa_units_included": pkg.wa_units_included,
        "web_units_included": pkg.web_units_included,
        "max_locations": pkg.max_locations,
        "promo_message_cost_minor": pkg.promo_message_cost_minor,
        "yearly_price_minor": price.yearly_price_minor,
        "is_frozen": bool(plan.is_frozen),
        "is_active": bool(plan.is_active and pkg.is_active),
        "currency": currency,
    }


def _sync_plan_marketing(plan, row: dict[str, Any]) -> None:
    import json

    locs = int(row.get("max_locations") or 0)
    wa = int(row.get("wa_units_included") or 0)
    web = int(row.get("web_units_included") or 0)
    web_label = "unlimited" if web < 0 else str(web)
    name = str(row.get("name") or plan.name or "Package").strip()
    plan.description = (
        f"WhatsApp + web QR feedback — {name} "
        f"({locs} location(s), {wa} WA + {web_label} web surveys/month)"
    )
    features = [
        f"{locs} location{'s' if locs != 1 else ''}",
        f"{wa:,} WhatsApp surveys/mo",
        "Unlimited web surveys/mo" if web < 0 else f"{web:,} web surveys/mo",
    ]
    plan.features_json = json.dumps(features)
    plan.whatsapp_included = wa


@router.post("/plans/pricing")
def create_pricing_row(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.models.plan import Plan
    from app.models.plan_price import PlanPrice
    from app.models.customer_feedback import FEEDBACK_SERVICE_CODE

    currency = str(payload.get("currency") or "GBP").upper()
    zone = str(payload.get("market_zone") or "gb").lower()
    name = str(payload.get("name") or "Enterprise").strip() or "Enterprise"
    suffix = uuid.uuid4().hex[:6]
    code = str(payload.get("code") or f"cf_enterprise_{zone}_{suffix}").strip().lower()
    if db.execute(select(Plan).where(Plan.code == code)).scalar_one_or_none():
        code = f"cf_enterprise_{zone}_{suffix}"

    now = datetime.utcnow()
    max_order = db.execute(
        select(func.max(FeedbackPackage.display_order)).where(FeedbackPackage.market_zone == zone)
    ).scalar()
    display_order = int(max_order or 0) + 10

    plan = Plan(
        id=str(uuid.uuid4()),
        code=code,
        name=name,
        price_gbp_pence=0,
        interval="monthly",
        service_kind=FEEDBACK_SERVICE_CODE,
        is_active=True,
        is_enterprise=True,
        is_featured=False,
        sort_order=display_order,
        created_at=now,
        updated_at=now,
    )
    db.add(plan)
    db.flush()

    pkg = FeedbackPackage(
        id=str(uuid.uuid4()),
        plan_id=plan.id,
        market_zone=zone,
        max_locations=1,
        wa_units_included=100,
        web_units_included=100,
        promo_message_cost_minor=5,
        display_order=display_order,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(pkg)

    price = PlanPrice(
        id=str(uuid.uuid4()),
        plan_id=plan.id,
        currency=currency,
        monthly_price_minor=0,
        yearly_price_minor=0,
        created_at=now,
        updated_at=now,
    )
    db.add(price)

    row = {
        "name": name,
        "max_locations": pkg.max_locations,
        "wa_units_included": pkg.wa_units_included,
        "web_units_included": pkg.web_units_included,
    }
    _sync_plan_marketing(plan, row)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    db.refresh(pkg)
    db.refresh(price)
    return {"ok": True, "item": _pricing_row_dict(plan, pkg, price, currency)}


@router.delete("/plans/pricing/{plan_id}")
def delete_pricing_row(plan_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.models.plan import Plan

    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    if bool(plan.is_frozen):
        raise HTTPException(status_code=400, detail="Frozen plans cannot be deleted")
    pkg = db.execute(select(FeedbackPackage).where(FeedbackPackage.plan_id == plan.id)).scalar_one_or_none()
    now = datetime.utcnow()
    plan.is_active = False
    plan.updated_at = now
    if pkg:
        pkg.is_active = False
        pkg.updated_at = now
        db.add(pkg)
    db.add(plan)
    db.commit()
    return {"ok": True, "plan_id": plan_id}


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
        if row.get("code") and not bool(plan.is_frozen):
            new_code = str(row.get("code")).strip().lower()
            if new_code and new_code != plan.code:
                existing = db.execute(select(Plan).where(Plan.code == new_code, Plan.id != plan.id)).scalar_one_or_none()
                if existing is None:
                    plan.code = new_code
        plan.is_active = bool(row.get("is_active", plan.is_active))
        if "is_frozen" in row:
            plan.is_frozen = bool(row.get("is_frozen"))
        plan.updated_at = now
        pkg.max_locations = int(row.get("max_locations") or pkg.max_locations or 1)
        pkg.wa_units_included = int(row.get("wa_units_included") or pkg.wa_units_included or 0)
        if "web_units_included" in row:
            pkg.web_units_included = int(row.get("web_units_included") or pkg.web_units_included or 0)
        pkg.promo_message_cost_minor = int(row.get("promo_message_cost_minor") or pkg.promo_message_cost_minor or 5)
        pkg.updated_at = now
        _sync_plan_marketing(plan, row)
        price = db.execute(
            select(PlanPrice).where(PlanPrice.plan_id == plan.id, PlanPrice.currency == currency)
        ).scalar_one_or_none()
        if price is None:
            price = PlanPrice(id=str(uuid.uuid4()), plan_id=plan.id, currency=currency, created_at=now, updated_at=now)
            db.add(price)
        price.monthly_price_minor = int(row.get("price_minor") or price.monthly_price_minor or 0)
        if "yearly_price_minor" in row:
            price.yearly_price_minor = int(row.get("yearly_price_minor") or price.yearly_price_minor or 0)
        elif price.monthly_price_minor:
            price.yearly_price_minor = int(price.monthly_price_minor) * 10
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
    from app.services.customer_feedback.feedback_telnyx_push_service import (
        FeedbackTelnyxPushError,
        push_all_feedback_templates_for_survey_type,
        refresh_feedback_template_status_from_telnyx_for_industry,
    )

    row = db.get(FeedbackSurveyType, survey_type_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Survey type not found")
    try:
        push_summary = push_all_feedback_templates_for_survey_type(db, survey_type_id=survey_type_id)
        refresh_summary = refresh_feedback_template_status_from_telnyx_for_industry(
            db, industry_id=row.industry_id
        )
    except FeedbackTelnyxPushError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": push_summary.get("ok", True),
        "push": push_summary,
        "refresh": refresh_summary,
        "message": " · ".join(
            [str(push_summary.get("message") or ""), str(refresh_summary.get("message") or "")]
        ).strip(" ·"),
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


@router.post("/wa-senders/sync-from-telnyx")
def sync_wa_senders_from_telnyx(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.customer_feedback.feedback_wa_phone import (
        get_telnyx_whatsapp_from_e164,
        sync_feedback_wa_senders_from_telnyx,
    )

    telnyx_phone = get_telnyx_whatsapp_from_e164(db)
    if not telnyx_phone:
        raise HTTPException(
            status_code=400,
            detail="Telnyx WhatsApp From is not set. Open Admin → Integrations → Telnyx and save your WhatsApp number.",
        )
    sync_feedback_wa_senders_from_telnyx(db)
    db.commit()
    rows = list(db.execute(select(FeedbackWaSender)).scalars().all())
    return {
        "ok": True,
        "telnyx_whatsapp_from": telnyx_phone,
        "items": [
            {"country_code": r.country_code, "phone_e164": r.phone_e164, "is_active": r.is_active}
            for r in rows
        ],
    }


@router.patch("/system-templates/{template_id}/sync-from-meta")
def patch_system_template_sync_from_meta(
    template_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    from app.services.customer_feedback.feedback_system_template_service import (
        FeedbackSystemTemplateError,
        FeedbackSystemTemplateService,
    )

    body = payload or {}
    try:
        return FeedbackSystemTemplateService.set_sync_from_meta(
            db, template_id, sync_from_meta=bool(body.get("sync_from_meta"))
        )
    except FeedbackSystemTemplateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/system-templates/{template_id}/pull-from-meta")
def pull_system_template_from_meta(
    template_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    from app.services.customer_feedback.feedback_system_template_service import (
        FeedbackSystemTemplateError,
        FeedbackSystemTemplateService,
    )

    try:
        return FeedbackSystemTemplateService.pull_one_from_meta(db, template_id)
    except FeedbackSystemTemplateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/system-templates")
def list_system_templates(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.customer_feedback.feedback_system_template_service import FeedbackSystemTemplateService

    return FeedbackSystemTemplateService.list_grouped_admin(db)


@router.post("/system-templates/pull-from-meta")
def pull_system_templates_from_meta(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.customer_feedback.feedback_system_template_service import FeedbackSystemTemplateService

    return FeedbackSystemTemplateService.pull_from_meta(db)


@router.post("/system-templates/push-all")
def push_all_system_templates(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.customer_feedback.feedback_system_template_service import FeedbackSystemTemplateService

    return FeedbackSystemTemplateService.push_all(db)


@router.post("/system-templates/{template_id}/push")
def push_system_template(
    template_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    from app.services.customer_feedback.feedback_system_template_service import (
        FeedbackSystemTemplateError,
        FeedbackSystemTemplateService,
    )

    try:
        return FeedbackSystemTemplateService.push_one(db, template_id)
    except FeedbackSystemTemplateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/wa-templates")
def list_wa_templates(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.customer_feedback.feedback_marketing_policy import is_marketing_wa_template

    rows = list(db.execute(select(FeedbackWaTemplate).order_by(FeedbackWaTemplate.step_order)).scalars().all())
    rows = [r for r in rows if not is_marketing_wa_template(r)]
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

    from app.services.customer_feedback.feedback_marketing_policy import marketing_wa_enabled

    proposed_category = str(payload.get("meta_category") or "utility").strip().lower()
    proposed_key = str(payload.get("template_key") or "").strip().lower()
    if not marketing_wa_enabled() and (proposed_category == "marketing" or proposed_key == "marketing_opt_in"):
        raise HTTPException(
            status_code=400,
            detail="Marketing-category WhatsApp templates are disabled on this platform.",
        )

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
    from app.services.wa_template_utility_content import is_promo_wording

    if is_promo_wording(row.body_text) or is_promo_wording(payload.get("template_key")):
        raise HTTPException(
            status_code=400,
            detail="Marketing words are not allowed in Utility feedback templates "
            "(e.g. promotion, discount, offer, sale, loyalty / خصم، عرض).",
        )
    if payload.get("step_role") is not None:
        row.step_role = str(payload.get("step_role") or "") or None
    if payload.get("language"):
        row.language = str(payload.get("language"))
    if payload.get("meta_category"):
        cat = str(payload.get("meta_category") or "utility").strip().lower()
        row.meta_category = "utility" if cat == "marketing" else cat
    if "buttons" in payload:
        buttons = payload.get("buttons")
        row.buttons_json = json.dumps(buttons) if isinstance(buttons, list) else None
    if "is_active" in payload:
        from app.services.wa_template_admin_visibility_service import apply_admin_survey_visibility

        visible = bool(payload.get("is_active"))
        apply_admin_survey_visibility(row, visible=visible)
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return {"ok": True, "item": FeedbackCatalogService.template_to_dict(row)}


@router.delete("/wa-templates/{template_id}")
def delete_wa_template(template_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    """Hard-delete feedback template from local DB and Meta."""
    from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
    from app.services.customer_feedback.feedback_telnyx_push_service import (
        english_anchor_template,
        feedback_meta_template_name,
    )
    from app.services.meta_whatsapp_template_service import MetaWhatsappTemplateService
    from app.services.whatsapp_provider_service import is_meta_whatsapp_primary

    row = db.get(FeedbackWaTemplate, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")
    meta_deleted = False
    name = None
    industry_slug = None
    survey_slug = None
    if row.industry_id:
        ind = db.get(FeedbackIndustry, row.industry_id)
        industry_slug = ind.slug if ind else None
    if row.survey_type_id:
        st = db.get(FeedbackSurveyType, row.survey_type_id)
        survey_slug = st.slug if st else None
    try:
        anchor = english_anchor_template(db, row)
        name = feedback_meta_template_name(
            row,
            industry_slug=industry_slug,
            survey_type_slug=survey_slug,
            name_anchor_id=anchor.id,
        )
    except Exception:
        name = None
    if name and is_meta_whatsapp_primary(db, service_code="customer_feedback"):
        try:
            MetaWhatsappTemplateService.delete_message_template(db, name=name)
            meta_deleted = True
        except Exception:
            # Still remove locally if Meta already gone or name unknown.
            pass
    # Drop matching catalog row(s) so hub counts stay accurate.
    if name:
        catalog_rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.name == name)
            ).scalars().all()
        )
        for catalog in catalog_rows:
            db.delete(catalog)
    db.delete(row)
    db.commit()
    return {
        "ok": True,
        "message": "Template deleted from Meta and database." if meta_deleted else "Template deleted from database.",
        "template_id": template_id,
        "meta_name": name,
        "meta_deleted": meta_deleted,
    }


@router.post("/wa-templates/{template_id}/push")
def push_wa_template(template_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.customer_feedback.feedback_telnyx_push_service import (
        FeedbackTelnyxPushError,
        push_feedback_template_to_telnyx,
    )
    from app.services.wa_template_closeout_service import WaTemplateCloseoutService

    row = db.get(FeedbackWaTemplate, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")
    WaTemplateCloseoutService.repair_feedback_content(db)
    row = db.get(FeedbackWaTemplate, template_id)
    try:
        return push_feedback_template_to_telnyx(db, row)
    except FeedbackTelnyxPushError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
