"""Customer dashboard API — VoxBulk Expo (WhatsApp exhibition lead capture)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.models.expo import ExpoBooth
from app.models.organisation import Organisation
from app.services.expo.asset_storage_service import save_expo_asset_upload
from app.services.expo.booth_service import ExpoBoothService
from app.services.expo.results_service import ExpoResultsService
from app.services.org_enabled_services import is_service_enabled, org_service_maps
from app.services.org_rbac import OrgRbacService

router = APIRouter(prefix="/expo", tags=["expo"])


def _require_expo_enabled(db: Session, org_id: str) -> None:
    org = db.get(Organisation, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    _allowed, _enabled, visible = org_service_maps(org, db)
    if not is_service_enabled(visible, "expo"):
        raise HTTPException(status_code=403, detail="VoxBulk Expo is not enabled for this organisation.")


def _campaign_owner_user_id(db: Session, principal) -> str | None:
    """Members are scoped to their own booths; owners/managers see all."""
    try:
        return OrgRbacService.campaign_owner_filter_for(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


def _get_owned_booth(db: Session, *, org_id: str, booth_id: str, owner_user_id: str | None) -> ExpoBooth:
    booth = ExpoBoothService.get_booth(db, org_id=org_id, booth_id=booth_id)
    if booth is None or (owner_user_id and booth.created_by_user_id != owner_user_id):
        raise HTTPException(status_code=404, detail="Booth not found")
    return booth


@router.get("/catalog/industries")
def list_industries(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_expo_enabled(db, principal.org_id)
    return {"ok": True, "items": ExpoBoothService.list_industries(db)}


@router.get("/catalog/questions")
def list_question_bank(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    """Selectable qualifying questions for the Expo wizard (plus optional industry addon)."""
    _require_expo_enabled(db, principal.org_id)
    from app.services.expo.question_bank import list_selectable_questions

    return {"ok": True, "items": list_selectable_questions(db)}


@router.get("/packages")
def list_packages(zone: str = "gb", db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    # Price list: campaign users need Expo enabled; billing roles may view packages for purchasing.
    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    _allowed, _enabled, visible = org_service_maps(org, db)
    expo_on = is_service_enabled(visible, "expo")
    if not expo_on:
        try:
            OrgRbacService.assert_can_access_billing(db, org_id=principal.org_id, user_id=principal.user_id)
        except PermissionError as e:
            raise HTTPException(
                status_code=403,
                detail="VoxBulk Expo is not enabled for this organisation.",
            ) from e
    return {"ok": True, "items": ExpoBoothService.list_packages(db, market_zone=zone)}


@router.get("/booths")
def list_booths(
    status: str | None = Query(None, description="active (default), archived, or all"),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    _require_expo_enabled(db, principal.org_id)
    owner_filter = _campaign_owner_user_id(db, principal)
    filt = str(status or "active").strip().lower() or "active"
    if filt not in ("active", "archived", "all"):
        filt = "active"
    return {
        "ok": True,
        "items": ExpoBoothService.list_booths(
            db, org_id=principal.org_id, owner_user_id=owner_filter, status_filter=filt
        ),
    }


@router.post("/booths")
def create_booth(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_expo_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_launch_campaigns(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    try:
        item = ExpoBoothService.create_booth(
            db, org_id=principal.org_id, user_id=principal.user_id, payload=payload
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "item": item}


@router.post("/booths/preview-draft")
def upsert_preview_draft(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    """Wizard Preview step — create/refresh draft booth so QR works; excluded from Saved booths."""
    _require_expo_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_launch_campaigns(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    try:
        item = ExpoBoothService.upsert_preview_draft(
            db, org_id=principal.org_id, user_id=principal.user_id, payload=payload
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "item": item}


@router.get("/profile")
def get_expo_profile(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_expo_enabled(db, principal.org_id)
    from app.services.expo.org_profile_service import ExpoOrgProfileService

    return {"ok": True, "item": ExpoOrgProfileService.get(db, principal.org_id)}


@router.post("/assets/upload")
async def upload_expo_asset(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    """Upload a PDF/image before creating a booth; returns storage_path to attach on create."""
    _require_expo_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_launch_campaigns(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    saved = await save_expo_asset_upload(org_id=principal.org_id, upload=file)
    return {"ok": True, "item": saved}


# --- Org catalogue library (Add catalogues page) ---


@router.get("/catalogue")
def get_expo_catalogue(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_expo_enabled(db, principal.org_id)
    from app.services.expo.library_catalogue_service import ExpoLibraryCatalogueService

    return {"ok": True, "categories": ExpoLibraryCatalogueService.tree(db, principal.org_id)}


@router.post("/catalogue/categories")
def create_expo_catalogue_category(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_expo_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_launch_campaigns(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    from app.services.expo.library_catalogue_service import ExpoLibraryCatalogueError, ExpoLibraryCatalogueService

    try:
        row = ExpoLibraryCatalogueService.create_category(db, org_id=principal.org_id, payload=payload or {})
        db.commit()
        return {"ok": True, "item": ExpoLibraryCatalogueService.serialize_category(row)}
    except ExpoLibraryCatalogueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.patch("/catalogue/categories/{category_id}")
def patch_expo_catalogue_category(
    category_id: str, payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)
):
    _require_expo_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_launch_campaigns(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    from app.services.expo.library_catalogue_service import ExpoLibraryCatalogueError, ExpoLibraryCatalogueService

    try:
        row = ExpoLibraryCatalogueService.update_category(
            db, org_id=principal.org_id, category_id=category_id, payload=payload or {}
        )
        db.commit()
        return {"ok": True, "item": ExpoLibraryCatalogueService.serialize_category(row)}
    except ExpoLibraryCatalogueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/catalogue/categories/{category_id}")
def delete_expo_catalogue_category(
    category_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)
):
    _require_expo_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_launch_campaigns(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    from app.services.expo.library_catalogue_service import ExpoLibraryCatalogueService

    ExpoLibraryCatalogueService.delete_category(db, org_id=principal.org_id, category_id=category_id)
    db.commit()
    return {"ok": True}


@router.post("/catalogue/products")
def create_expo_catalogue_product(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_expo_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_launch_campaigns(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    from app.services.expo.library_catalogue_service import ExpoLibraryCatalogueError, ExpoLibraryCatalogueService

    try:
        row = ExpoLibraryCatalogueService.create_product(db, org_id=principal.org_id, payload=payload or {})
        db.commit()
        return {"ok": True, "item": ExpoLibraryCatalogueService.serialize_product(row)}
    except ExpoLibraryCatalogueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.patch("/catalogue/products/{product_id}")
def patch_expo_catalogue_product(
    product_id: str, payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)
):
    _require_expo_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_launch_campaigns(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    from app.services.expo.library_catalogue_service import ExpoLibraryCatalogueError, ExpoLibraryCatalogueService

    try:
        row = ExpoLibraryCatalogueService.update_product(
            db, org_id=principal.org_id, product_id=product_id, payload=payload or {}
        )
        db.commit()
        return {"ok": True, "item": ExpoLibraryCatalogueService.serialize_product(row)}
    except ExpoLibraryCatalogueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/catalogue/products/{product_id}")
def delete_expo_catalogue_product(
    product_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)
):
    _require_expo_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_launch_campaigns(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    from app.services.expo.library_catalogue_service import ExpoLibraryCatalogueService

    ExpoLibraryCatalogueService.delete_product(db, org_id=principal.org_id, product_id=product_id)
    db.commit()
    return {"ok": True}


@router.post("/catalogue/assets/upload")
async def upload_expo_catalogue_asset(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    _require_expo_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_launch_campaigns(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    saved = await save_expo_asset_upload(org_id=principal.org_id, upload=file)
    return {"ok": True, "item": saved}


@router.post("/catalogue/assets")
def create_expo_catalogue_asset(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_expo_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_launch_campaigns(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    from app.services.expo.library_catalogue_service import ExpoLibraryCatalogueError, ExpoLibraryCatalogueService

    try:
        row = ExpoLibraryCatalogueService.create_asset(db, org_id=principal.org_id, payload=payload or {})
        db.commit()
        return {"ok": True, "item": ExpoLibraryCatalogueService.serialize_asset(row)}
    except ExpoLibraryCatalogueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/catalogue/assets/{asset_id}")
def delete_expo_catalogue_asset(asset_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_expo_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_launch_campaigns(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    from app.services.expo.library_catalogue_service import ExpoLibraryCatalogueService

    ExpoLibraryCatalogueService.delete_asset(db, org_id=principal.org_id, asset_id=asset_id)
    db.commit()
    return {"ok": True}


@router.get("/booths/{booth_id}")
def get_booth(booth_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_expo_enabled(db, principal.org_id)
    owner_filter = _campaign_owner_user_id(db, principal)
    booth = _get_owned_booth(db, org_id=principal.org_id, booth_id=booth_id, owner_user_id=owner_filter)
    return {"ok": True, "item": ExpoBoothService.serialize_booth(db, booth)}


@router.patch("/booths/{booth_id}")
def patch_booth(booth_id: str, payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    """Update event, questions, closing, representatives, and product categories (QR token stays)."""
    _require_expo_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_launch_campaigns(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    owner_filter = _campaign_owner_user_id(db, principal)
    _get_owned_booth(db, org_id=principal.org_id, booth_id=booth_id, owner_user_id=owner_filter)
    try:
        item = ExpoBoothService.update_booth(
            db, org_id=principal.org_id, booth_id=booth_id, payload=payload or {}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "item": item}

@router.get("/booths/{booth_id}/pay/options")
def booth_pay_options(booth_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    """Available Stripe / Airwallex rails + package amount for Expo go-live checkout."""
    from app.services.expo.booth_payment_service import ExpoBoothPaymentError, ExpoBoothPaymentService

    _require_expo_enabled(db, principal.org_id)
    owner_filter = _campaign_owner_user_id(db, principal)
    booth = _get_owned_booth(db, org_id=principal.org_id, booth_id=booth_id, owner_user_id=owner_filter)
    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    try:
        return ExpoBoothPaymentService.pay_options(db, org=org, booth=booth)
    except ExpoBoothPaymentError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/booths/{booth_id}/pay/intent")
def booth_pay_intent(
    booth_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.airwallex_payment_service import (
        AirwallexConfigError,
        AirwallexProviderError,
    )
    from app.services.expo.booth_payment_service import ExpoBoothPaymentError, ExpoBoothPaymentService
    from app.services.stripe_payment_service import StripeConfigError, StripeProviderError

    _require_expo_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_launch_campaigns(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    owner_filter = _campaign_owner_user_id(db, principal)
    booth = _get_owned_booth(db, org_id=principal.org_id, booth_id=booth_id, owner_user_id=owner_filter)
    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    provider = str((payload or {}).get("provider") or "").strip().lower()
    try:
        return ExpoBoothPaymentService.create_intent(db, org=org, booth=booth, provider=provider)
    except ExpoBoothPaymentError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (StripeConfigError, AirwallexConfigError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (StripeProviderError, AirwallexProviderError) as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/booths/{booth_id}/pay/confirm")
def booth_pay_confirm(
    booth_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.airwallex_payment_service import (
        AirwallexConfigError,
        AirwallexProviderError,
    )
    from app.services.expo.booth_payment_service import ExpoBoothPaymentError, ExpoBoothPaymentService
    from app.services.stripe_payment_service import StripeConfigError, StripeProviderError

    _require_expo_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_launch_campaigns(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    owner_filter = _campaign_owner_user_id(db, principal)
    booth = _get_owned_booth(db, org_id=principal.org_id, booth_id=booth_id, owner_user_id=owner_filter)
    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    provider = str((payload or {}).get("provider") or "").strip().lower()
    intent_id = str((payload or {}).get("payment_intent_id") or "").strip()
    try:
        return ExpoBoothPaymentService.confirm(
            db, org=org, booth=booth, provider=provider, payment_intent_id=intent_id
        )
    except ExpoBoothPaymentError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (StripeConfigError, AirwallexConfigError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (StripeProviderError, AirwallexProviderError) as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.delete("/booths/{booth_id}")
def delete_booth(booth_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_expo_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_launch_campaigns(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    owner_filter = _campaign_owner_user_id(db, principal)
    _get_owned_booth(db, org_id=principal.org_id, booth_id=booth_id, owner_user_id=owner_filter)
    try:
        ExpoBoothService.delete_booth(db, org_id=principal.org_id, booth_id=booth_id)
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg) from e
    return {"ok": True}


@router.post("/booths/{booth_id}/archive")
def archive_booth(booth_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_expo_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_launch_campaigns(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    owner_filter = _campaign_owner_user_id(db, principal)
    _get_owned_booth(db, org_id=principal.org_id, booth_id=booth_id, owner_user_id=owner_filter)
    try:
        item = ExpoBoothService.archive_booth(db, org_id=principal.org_id, booth_id=booth_id)
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg) from e
    return {"ok": True, "item": item}


@router.post("/booths/{booth_id}/restore")
def restore_booth(booth_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_expo_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_launch_campaigns(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    owner_filter = _campaign_owner_user_id(db, principal)
    _get_owned_booth(db, org_id=principal.org_id, booth_id=booth_id, owner_user_id=owner_filter)
    try:
        item = ExpoBoothService.restore_booth(db, org_id=principal.org_id, booth_id=booth_id)
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg) from e
    return {"ok": True, "item": item}


@router.get("/results/summary")
def results_summary(
    booth_id: str | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    _require_expo_enabled(db, principal.org_id)
    owner_filter = _campaign_owner_user_id(db, principal)
    return ExpoResultsService.customer_summary(
        db, principal.org_id, booth_id=booth_id, created_by_user_id=owner_filter
    )


@router.get("/results/leads")
def results_leads(
    booth_id: str | None = None,
    score: str | None = None,
    catalogue_requested: bool | None = None,
    price_list_requested: bool | None = None,
    asset_opened: bool | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    _require_expo_enabled(db, principal.org_id)
    owner_filter = _campaign_owner_user_id(db, principal)
    items = ExpoResultsService.customer_leads(
        db,
        principal.org_id,
        booth_id=booth_id,
        score=score,
        catalogue_requested=catalogue_requested,
        price_list_requested=price_list_requested,
        asset_opened=asset_opened,
        created_by_user_id=owner_filter,
    )
    return {"ok": True, "items": items}


@router.delete("/results/leads/{lead_id}")
def delete_lead(lead_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_expo_enabled(db, principal.org_id)
    try:
        OrgRbacService.assert_can_launch_campaigns(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    owner_filter = _campaign_owner_user_id(db, principal)
    try:
        ExpoResultsService.delete_lead(
            db, principal.org_id, lead_id=lead_id, created_by_user_id=owner_filter
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"ok": True}


@router.get("/results/leads/{lead_id}")
def get_lead_detail(lead_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_expo_enabled(db, principal.org_id)
    owner_filter = _campaign_owner_user_id(db, principal)
    try:
        item = ExpoResultsService.lead_detail(
            db, principal.org_id, lead_id=lead_id, created_by_user_id=owner_filter
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"ok": True, "item": item}


@router.get("/results/leads/{lead_id}/card-image")
def get_lead_card_image(lead_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from fastapi.responses import FileResponse

    _require_expo_enabled(db, principal.org_id)
    owner_filter = _campaign_owner_user_id(db, principal)
    path = ExpoResultsService.resolve_lead_card_path(
        db, principal.org_id, lead_id=lead_id, created_by_user_id=owner_filter
    )
    if path is None:
        raise HTTPException(status_code=404, detail="Business card image not found")
    suffix = path.suffix.lower()
    media = "image/jpeg"
    if suffix == ".png":
        media = "image/png"
    elif suffix == ".webp":
        media = "image/webp"
    elif suffix == ".gif":
        media = "image/gif"
    return FileResponse(path, media_type=media, filename=path.name)


@router.get("/results/export.csv")
def results_export_csv(
    booth_id: str | None = None,
    lead_id: str | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    _require_expo_enabled(db, principal.org_id)
    owner_filter = _campaign_owner_user_id(db, principal)
    csv_text = ExpoResultsService.export_csv(
        db,
        principal.org_id,
        booth_id=booth_id or None,
        lead_id=lead_id or None,
        created_by_user_id=owner_filter,
    )
    suffix = (lead_id or booth_id or "all")[:8]
    # BOM so Excel opens UTF-8 correctly
    body = ("\ufeff" + csv_text).encode("utf-8")
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="expo-leads-{suffix}.csv"'},
    )


@router.get("/results/export.xlsx")
def results_export_xlsx(
    booth_id: str | None = None,
    lead_id: str | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    _require_expo_enabled(db, principal.org_id)
    owner_filter = _campaign_owner_user_id(db, principal)
    try:
        xlsx_bytes = ExpoResultsService.export_xlsx(
            db,
            principal.org_id,
            booth_id=booth_id or None,
            lead_id=lead_id or None,
            created_by_user_id=owner_filter,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    suffix = (lead_id or booth_id or "all")[:8]
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="expo-leads-{suffix}.xlsx"'},
    )


@router.get("/results/export")
def results_export(
    format: str = "xlsx",
    booth_id: str | None = None,
    lead_id: str | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    """Alias without a file extension in the path (avoids nginx static .csv/.xlsx quirks)."""
    fmt = str(format or "xlsx").strip().lower()
    if fmt in {"xlsx", "excel", "xls"}:
        return results_export_xlsx(booth_id=booth_id, lead_id=lead_id, db=db, principal=principal)
    return results_export_csv(booth_id=booth_id, lead_id=lead_id, db=db, principal=principal)
