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
                "key": r.question_key,
                "label": r.label,
                "prompt": r.prompt,
                "description": r.description,
                "kind": r.kind,
                "sort_order": r.sort_order,
            }
            for r in rows
        ],
    }


@router.get("/catalog/questions")
def catalog_questions(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    """Selectable question bank for the setup wizard (Expo-style)."""
    _require_smart_card_enabled(db, principal.org_id)
    from app.services.smart_card.seed_service import SmartCardSeedService

    SmartCardSeedService._ensure_question_templates(db)
    db.commit()
    rows = (
        db.execute(
            select(SmartCardQuestionTemplate)
            .where(
                SmartCardQuestionTemplate.is_active.is_(True),
                SmartCardQuestionTemplate.kind == "selectable",
            )
            .order_by(SmartCardQuestionTemplate.sort_order.asc())
        )
        .scalars()
        .all()
    )
    return {
        "ok": True,
        "items": [
            {
                "key": r.question_key,
                "question_key": r.question_key,
                "label": r.label,
                "prompt": r.prompt,
                "description": r.description or "",
                "matches_products": r.question_key
                in {"interest", "products_wanted", "need_price_list", "need_catalogue"},
            }
            for r in rows
        ],
    }


@router.post("/setup/preview-draft")
def setup_preview_draft(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    """Wizard Preview — persist company, questions, optional catalogue, first rep + QR."""
    _require_smart_card_enabled(db, principal.org_id)
    _require_manage(db, principal)
    from app.services.smart_card.setup_service import SmartCardSetupError, SmartCardSetupService

    try:
        result = SmartCardSetupService.preview_draft(
            db, org_id=principal.org_id, user_id=principal.user_id, payload=payload or {}
        )
        db.commit()
        return {"ok": True, **result}
    except SmartCardSetupError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/setup/activate")
def setup_activate(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    """Start seat checkout after wizard (plan_id + seat_quantity). Reuses billing checkout."""
    _require_smart_card_enabled(db, principal.org_id)
    _require_manage(db, principal)
    from app.services.smart_card.billing_service import SmartCardBillingError, SmartCardBillingService

    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    try:
        from app.models.user import User

        user = db.get(User, principal.user_id)
        checkout = SmartCardBillingService.start_seat_checkout(
            db,
            org=org,
            plan_id=str((payload or {}).get("plan_id") or "").strip(),
            seat_quantity=int((payload or {}).get("seat_quantity") or 0),
            user_email=str(getattr(user, "email", "") or ""),
            provider=(str((payload or {}).get("provider") or "").strip() or None),
            billing_interval=str((payload or {}).get("billing_interval") or "yearly").strip() or "yearly",
        )
        db.commit()
        return {"ok": True, **checkout}
    except SmartCardBillingError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail="Invalid seat_quantity or plan_id") from e


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


@router.post("/representatives/{rep_id}/photo")
async def upload_rep_photo(
    rep_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    _require_smart_card_enabled(db, principal.org_id)
    _require_manage(db, principal)
    from pathlib import Path

    rep = SmartCardRepresentativeService.get(db, org_id=principal.org_id, rep_id=rep_id)
    if rep is None:
        raise HTTPException(status_code=404, detail="Representative not found")
    raw = await file.read()
    if not raw or len(raw) > 3 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Photo must be under 3 MB")
    ext = Path(file.filename or "photo.jpg").suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=400, detail="Photo must be PNG, JPG, or WEBP")
    rel = f"data/smart_card_photos/{principal.org_id}/{rep.id}{ext}"
    abs_path = Path(__file__).resolve().parents[2] / rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(raw)
    rep.photo_storage_path = rel.replace("\\", "/")
    db.add(rep)
    db.commit()
    return {"ok": True, "item": SmartCardRepresentativeService.serialize(db, rep)}


@router.get("/representatives/{rep_id}/photo")
def get_rep_photo(rep_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from pathlib import Path

    from fastapi.responses import FileResponse

    _require_smart_card_enabled(db, principal.org_id)
    rep = SmartCardRepresentativeService.get(db, org_id=principal.org_id, rep_id=rep_id)
    if rep is None or not rep.photo_storage_path:
        raise HTTPException(status_code=404, detail="Photo not found")
    role = OrgRbacService.role_for(db, org_id=principal.org_id, user_id=principal.user_id)
    if not can_view_all_campaigns(role) and rep.linked_user_id != principal.user_id:
        raise HTTPException(status_code=404, detail="Photo not found")
    abs_path = (Path(__file__).resolve().parents[2] / str(rep.photo_storage_path)).resolve()
    if not abs_path.is_file():
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(abs_path)


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
            db,
            org_id=principal.org_id,
            name=str((payload or {}).get("name") or ""),
            sort_order=int((payload or {}).get("sort_order") or 100),
            accent_color=(payload or {}).get("accent_color") or (payload or {}).get("color"),
            is_frozen=(payload or {}).get("is_frozen") if "is_frozen" in (payload or {}) else (payload or {}).get("frozen"),
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
def results_summary(
    representative_id: str | None = Query(None),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    _require_smart_card_enabled(db, principal.org_id)
    from app.services.smart_card.results_service import SmartCardResultsService

    return {
        "ok": True,
        **SmartCardResultsService.customer_summary(
            db,
            org_id=principal.org_id,
            user_id=principal.user_id,
            representative_id=representative_id,
        ),
    }


@router.get("/results/leads")
def list_leads(
    representative_id: str | None = Query(None),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    _require_smart_card_enabled(db, principal.org_id)
    from app.services.smart_card.results_service import SmartCardResultsService

    return {
        "ok": True,
        "items": SmartCardResultsService.list_leads(
            db,
            org_id=principal.org_id,
            user_id=principal.user_id,
            representative_id=representative_id,
        ),
    }


@router.get("/results/leads/{lead_id}")
def get_lead(lead_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    from app.services.smart_card.results_service import SmartCardResultsError, SmartCardResultsService

    try:
        item = SmartCardResultsService.get_lead(
            db, org_id=principal.org_id, user_id=principal.user_id, lead_id=lead_id
        )
        return {"ok": True, "item": item}
    except SmartCardResultsError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/results/leads/{lead_id}/card-image")
def get_lead_card_image(
    lead_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)
):
    _require_smart_card_enabled(db, principal.org_id)
    from fastapi.responses import FileResponse

    from app.services.smart_card.results_service import SmartCardResultsError, SmartCardResultsService

    try:
        path = SmartCardResultsService.resolve_lead_card_path(
            db, org_id=principal.org_id, user_id=principal.user_id, lead_id=lead_id
        )
    except SmartCardResultsError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    if path is None:
        raise HTTPException(status_code=404, detail="Card image not found")
    return FileResponse(path)


@router.get("/results/voice-notes/{job_id}/audio")
def get_voice_note_audio(
    job_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)
):
    _require_smart_card_enabled(db, principal.org_id)
    from fastapi.responses import FileResponse

    from app.services.smart_card.results_service import SmartCardResultsService

    path = SmartCardResultsService.resolve_voice_audio_path(
        db, org_id=principal.org_id, user_id=principal.user_id, job_id=job_id
    )
    if path is None:
        raise HTTPException(status_code=404, detail="Audio not found")
    media = "audio/webm"
    suffix = path.suffix.lower()
    if suffix in {".ogg", ".oga"}:
        media = "audio/ogg"
    elif suffix in {".mp3", ".mpeg"}:
        media = "audio/mpeg"
    elif suffix in {".wav"}:
        media = "audio/wav"
    elif suffix in {".m4a", ".mp4"}:
        media = "audio/mp4"
    return FileResponse(path, media_type=media)


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
            billing_interval=str((payload or {}).get("billing_interval") or "yearly").strip() or "yearly",
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
            billing_interval=str((payload or {}).get("billing_interval") or "").strip() or None,
        )
        db.commit()
        return {
            "ok": True,
            "subscription_id": sub.id,
            "seat_quantity": int(sub.seat_quantity or 0),
            "status": sub.status,
            "billing_interval": getattr(sub, "billing_interval", None),
            "period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
        }
    except SmartCardBillingError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/billing/gocardless/start")
def start_smart_card_gocardless(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_access_billing(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    from app.services.smart_card.billing_service import SmartCardBillingError, SmartCardBillingService

    try:
        res = SmartCardBillingService.start_gocardless_signup(
            db,
            org_id=principal.org_id,
            user_id=principal.user_id,
            plan_id=str((payload or {}).get("plan_id") or ""),
            seat_quantity=int((payload or {}).get("seat_quantity") or 0),
            billing_interval=str((payload or {}).get("billing_interval") or "monthly").strip() or "monthly",
        )
        db.commit()
        return {"ok": True, **res}
    except SmartCardBillingError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail="Invalid seat_quantity or plan_id") from e


@router.post("/billing/gocardless/complete")
def complete_smart_card_gocardless(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_access_billing(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    from app.services.gocardless_service import BillingService, GoCardlessConfigError, GoCardlessProviderError

    redirect_flow_id = str((payload or {}).get("redirect_flow_id") or "").strip()
    if not redirect_flow_id:
        raise HTTPException(status_code=400, detail="redirect_flow_id required")
    try:
        res = BillingService.complete_gocardless_redirect_flow(
            db,
            org_id=principal.org_id,
            user_id=principal.user_id,
            redirect_flow_id=redirect_flow_id,
        )
        return {"ok": True, **{k: v for k, v in res.items() if k != "subscription"}}
    except (GoCardlessConfigError, GoCardlessProviderError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
