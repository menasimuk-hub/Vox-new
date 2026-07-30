"""Customer dashboard API — Smart Card QR."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.plan_price import PlanPrice
from app.models.smart_card import SMART_CARD_SERVICE_CODE, SmartCardPackage, SmartCardQuestionTemplate
from app.services.org_enabled_services import is_service_enabled, org_service_maps
from app.services.org_rbac import OrgRbacService, can_view_all_campaigns
from app.services.smart_card.asset_storage_service import save_smart_card_asset_upload
from app.services.smart_card.company_service import SmartCardCompanyService, SmartCardEntitlementService
from app.services.smart_card.representative_service import SmartCardRepError, SmartCardRepresentativeService

router = APIRouter(prefix="/smart-card", tags=["smart-card"])


def _require_smart_card_enabled(db: Session, org_id: str) -> None:
    org = db.get(Organisation, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    _allowed, _enabled, visible = org_service_maps(org, db)
    if not is_service_enabled(visible, "smart_card"):
        raise HTTPException(status_code=403, detail="Smart Card QR is not enabled for this organisation.")


def _require_manage(db: Session, principal) -> None:
    try:
        OrgRbacService.assert_can_manage_team(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.get("/entitlement")
def get_entitlement(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    mode = SmartCardEntitlementService.access_mode(db, principal.org_id)
    company = SmartCardCompanyService.get_or_create(db, principal.org_id)
    sub = SmartCardEntitlementService.active_subscription(db, principal.org_id)
    return {
        "ok": True,
        "mode": mode,
        "seat_quantity": SmartCardEntitlementService.seat_quantity(db, principal.org_id),
        "active_reps": SmartCardEntitlementService.active_rep_count(db, principal.org_id),
        "preview_tests_used": int(company.preview_tests_used or 0),
        "preview_tests_limit": 15,
        "period_end": sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
        "subscription_id": sub.id if sub else None,
    }


@router.get("/company")
def get_company(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    company = SmartCardCompanyService.get_or_create(db, principal.org_id)
    db.commit()
    return {"ok": True, "company": SmartCardCompanyService.serialize(company)}


@router.patch("/company")
def patch_company(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    _require_manage(db, principal)
    company = SmartCardCompanyService.update(db, principal.org_id, payload or {})
    db.commit()
    return {"ok": True, "company": SmartCardCompanyService.serialize(company)}


@router.get("/questions")
def list_questions(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    rows = (
        db.execute(
            select(SmartCardQuestionTemplate)
            .where(SmartCardQuestionTemplate.is_active.is_(True))
            .order_by(SmartCardQuestionTemplate.sort_order.asc())
        )
        .scalars()
        .all()
    )
    return {
        "ok": True,
        "items": [
            {
                "question_key": r.question_key,
                "label": r.label,
                "prompt": r.prompt,
                "description": r.description,
                "kind": r.kind,
                "sort_order": r.sort_order,
            }
            for r in rows
        ],
    }


@router.get("/packages")
def list_packages(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    _allowed, _enabled, visible = org_service_maps(org, db)
    if not is_service_enabled(visible, "smart_card"):
        try:
            OrgRbacService.assert_can_access_billing(db, org_id=principal.org_id, user_id=principal.user_id)
        except PermissionError as e:
            raise HTTPException(status_code=403, detail="Smart Card QR is not enabled for this organisation.") from e

    pkgs = (
        db.execute(
            select(SmartCardPackage, Plan)
            .join(Plan, Plan.id == SmartCardPackage.plan_id)
            .where(SmartCardPackage.is_active.is_(True), Plan.is_active.is_(True))
            .order_by(SmartCardPackage.display_order.asc())
        )
        .all()
    )
    items = []
    for sc_pkg, plan in pkgs:
        prices = (
            db.execute(select(PlanPrice).where(PlanPrice.plan_id == plan.id)).scalars().all()
        )
        items.append(
            {
                "id": sc_pkg.id,
                "plan_id": plan.id,
                "code": plan.code,
                "name": plan.name,
                "description": plan.description,
                "tier": sc_pkg.tier,
                "interval": plan.interval,
                "features": plan.features_json,
                "prices": [
                    {
                        "currency": p.currency,
                        "monthly_price_minor": p.monthly_price_minor,
                        "yearly_price_minor": p.yearly_price_minor,
                    }
                    for p in prices
                ],
            }
        )
    return {"ok": True, "items": items, "service_kind": SMART_CARD_SERVICE_CODE}


@router.get("/representatives")
def list_reps(
    q: str | None = Query(None),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    _require_smart_card_enabled(db, principal.org_id)
    rows = SmartCardRepresentativeService.list_for_user(
        db, org_id=principal.org_id, user_id=principal.user_id, q=q
    )
    return {
        "ok": True,
        "items": [SmartCardRepresentativeService.serialize(db, r) for r in rows],
    }


@router.post("/representatives")
def create_rep(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    _require_manage(db, principal)
    try:
        rep = SmartCardRepresentativeService.create(
            db, org_id=principal.org_id, user_id=principal.user_id, payload=payload or {}
        )
        db.commit()
        return {"ok": True, "item": SmartCardRepresentativeService.serialize(db, rep)}
    except SmartCardRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/representatives/{rep_id}")
def get_rep(rep_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    rep = SmartCardRepresentativeService.get(db, org_id=principal.org_id, rep_id=rep_id)
    if rep is None:
        raise HTTPException(status_code=404, detail="Representative not found")
    role = OrgRbacService.role_for(db, org_id=principal.org_id, user_id=principal.user_id)
    if not can_view_all_campaigns(role) and rep.linked_user_id != principal.user_id:
        raise HTTPException(status_code=404, detail="Representative not found")
    return {"ok": True, "item": SmartCardRepresentativeService.serialize(db, rep)}


@router.patch("/representatives/{rep_id}")
def patch_rep(rep_id: str, payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    _require_manage(db, principal)
    try:
        rep = SmartCardRepresentativeService.update(
            db, org_id=principal.org_id, rep_id=rep_id, payload=payload or {}
        )
        db.commit()
        return {"ok": True, "item": SmartCardRepresentativeService.serialize(db, rep)}
    except SmartCardRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# --- Catalogue ---


@router.get("/catalogue")
def get_catalogue(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    from app.services.smart_card.catalogue_service import SmartCardCatalogueService

    return {"ok": True, "categories": SmartCardCatalogueService.tree(db, principal.org_id)}


@router.post("/catalogue/categories")
def create_category(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    _require_manage(db, principal)
    from app.services.smart_card.catalogue_service import SmartCardCatalogueError, SmartCardCatalogueService

    try:
        row = SmartCardCatalogueService.create_category(
            db, org_id=principal.org_id, name=str((payload or {}).get("name") or "")
        )
        db.commit()
        return {"ok": True, "item": SmartCardCatalogueService.serialize_category(row)}
    except SmartCardCatalogueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.patch("/catalogue/categories/{category_id}")
def patch_category(
    category_id: str, payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)
):
    _require_smart_card_enabled(db, principal.org_id)
    _require_manage(db, principal)
    from app.services.smart_card.catalogue_service import SmartCardCatalogueError, SmartCardCatalogueService

    try:
        row = SmartCardCatalogueService.update_category(
            db, org_id=principal.org_id, category_id=category_id, payload=payload or {}
        )
        db.commit()
        return {"ok": True, "item": SmartCardCatalogueService.serialize_category(row)}
    except SmartCardCatalogueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/catalogue/categories/{category_id}")
def delete_category(category_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    _require_manage(db, principal)
    from app.services.smart_card.catalogue_service import SmartCardCatalogueService

    SmartCardCatalogueService.delete_category(db, org_id=principal.org_id, category_id=category_id)
    db.commit()
    return {"ok": True}


@router.post("/catalogue/products")
def create_product(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    _require_manage(db, principal)
    from app.services.smart_card.catalogue_service import SmartCardCatalogueError, SmartCardCatalogueService

    try:
        row = SmartCardCatalogueService.create_product(db, org_id=principal.org_id, payload=payload or {})
        db.commit()
        return {"ok": True, "item": SmartCardCatalogueService.serialize_product(row)}
    except SmartCardCatalogueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.patch("/catalogue/products/{product_id}")
def patch_product(
    product_id: str, payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)
):
    _require_smart_card_enabled(db, principal.org_id)
    _require_manage(db, principal)
    from app.services.smart_card.catalogue_service import SmartCardCatalogueError, SmartCardCatalogueService

    try:
        row = SmartCardCatalogueService.update_product(
            db, org_id=principal.org_id, product_id=product_id, payload=payload or {}
        )
        db.commit()
        return {"ok": True, "item": SmartCardCatalogueService.serialize_product(row)}
    except SmartCardCatalogueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/catalogue/products/{product_id}")
def delete_product(product_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    _require_manage(db, principal)
    from app.services.smart_card.catalogue_service import SmartCardCatalogueService

    SmartCardCatalogueService.delete_product(db, org_id=principal.org_id, product_id=product_id)
    db.commit()
    return {"ok": True}


@router.post("/catalogue/assets/upload")
async def upload_catalogue_asset(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    """Upload a PDF/image before creating a catalogue asset; returns storage_path to attach on create."""
    _require_smart_card_enabled(db, principal.org_id)
    _require_manage(db, principal)
    saved = await save_smart_card_asset_upload(org_id=principal.org_id, upload=file)
    return {"ok": True, "item": saved}


@router.post("/catalogue/assets")
def create_asset(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    _require_manage(db, principal)
    from app.services.smart_card.catalogue_service import SmartCardCatalogueError, SmartCardCatalogueService

    try:
        row = SmartCardCatalogueService.create_asset(db, org_id=principal.org_id, payload=payload or {})
        db.commit()
        return {"ok": True, "item": SmartCardCatalogueService.serialize_asset(row)}
    except SmartCardCatalogueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/catalogue/assets/{asset_id}")
def delete_asset(asset_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    _require_manage(db, principal)
    from app.services.smart_card.catalogue_service import SmartCardCatalogueService

    SmartCardCatalogueService.delete_asset(db, org_id=principal.org_id, asset_id=asset_id)
    db.commit()
    return {"ok": True}


# --- Leads & KPIs ---


@router.get("/results/summary")
def results_summary(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    from app.services.smart_card.results_service import SmartCardResultsService

    return {"ok": True, **SmartCardResultsService.customer_summary(db, org_id=principal.org_id, user_id=principal.user_id)}


@router.get("/results/leads")
def list_leads(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    from app.services.smart_card.results_service import SmartCardResultsService

    return {
        "ok": True,
        "items": SmartCardResultsService.list_leads(db, org_id=principal.org_id, user_id=principal.user_id),
    }


@router.patch("/results/leads/{lead_id}")
def patch_lead(lead_id: str, payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    from app.services.smart_card.results_service import SmartCardResultsError, SmartCardResultsService

    try:
        item = SmartCardResultsService.update_lead(
            db,
            org_id=principal.org_id,
            user_id=principal.user_id,
            lead_id=lead_id,
            payload=payload or {},
        )
        db.commit()
        return {"ok": True, "item": item}
    except SmartCardResultsError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# --- Change requests ---


@router.get("/change-requests")
def list_change_requests(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    from app.services.smart_card.change_request_service import SmartCardChangeRequestService

    return {
        "ok": True,
        "items": SmartCardChangeRequestService.list_for_user(
            db, org_id=principal.org_id, user_id=principal.user_id
        ),
    }


@router.post("/change-requests")
def create_change_request(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    from app.services.smart_card.change_request_service import SmartCardChangeRequestError, SmartCardChangeRequestService

    try:
        item = SmartCardChangeRequestService.create(
            db, org_id=principal.org_id, user_id=principal.user_id, payload=payload or {}
        )
        db.commit()
        return {"ok": True, "item": item}
    except SmartCardChangeRequestError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.patch("/change-requests/{request_id}")
def patch_change_request(
    request_id: str, payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)
):
    _require_smart_card_enabled(db, principal.org_id)
    _require_manage(db, principal)
    from app.services.smart_card.change_request_service import SmartCardChangeRequestError, SmartCardChangeRequestService

    try:
        item = SmartCardChangeRequestService.resolve(
            db,
            org_id=principal.org_id,
            user_id=principal.user_id,
            request_id=request_id,
            payload=payload or {},
        )
        db.commit()
        return {"ok": True, "item": item}
    except SmartCardChangeRequestError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# --- Seat checkout ---


@router.post("/billing/checkout")
def start_seat_checkout(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_access_billing(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    from app.services.smart_card.billing_service import SmartCardBillingError, SmartCardBillingService

    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    try:
        checkout = SmartCardBillingService.start_seat_checkout(
            db,
            org=org,
            plan_id=str((payload or {}).get("plan_id") or ""),
            seat_quantity=int((payload or {}).get("seat_quantity") or 0),
            user_email=str(getattr(principal, "email", "") or ""),
            provider=(str((payload or {}).get("provider") or "").strip() or None),
        )
        db.commit()
        return {"ok": True, **checkout}
    except SmartCardBillingError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail="Invalid seat_quantity or plan_id") from e


@router.post("/billing/complete")
def complete_seat_checkout(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_access_billing(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    from app.services.smart_card.billing_service import SmartCardBillingError, SmartCardBillingService

    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    try:
        seats = (payload or {}).get("seat_quantity")
        sub = SmartCardBillingService.complete_seat_checkout(
            db,
            org=org,
            plan_id=str((payload or {}).get("plan_id") or ""),
            provider=str((payload or {}).get("provider") or ""),
            payment_intent_id=str((payload or {}).get("payment_intent_id") or ""),
            seat_quantity=int(seats) if seats is not None else None,
        )
        db.commit()
        return {
            "ok": True,
            "subscription_id": sub.id,
            "seat_quantity": int(sub.seat_quantity or 0),
            "status": sub.status,
            "period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
        }
    except SmartCardBillingError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
