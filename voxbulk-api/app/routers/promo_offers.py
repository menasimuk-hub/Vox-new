from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.admin_rbac import require_platform_admin
from app.core.database import get_db
from app.core.dependencies import CurrentPrincipal, get_current_principal
from app.models.promo_offer import PromoOffer
from app.services.promo_offer_service import PromoOfferError, PromoOfferService

router = APIRouter(tags=["promo"])


@router.get("/promo/{code}")
def public_promo_preview(code: str, db: Session = Depends(get_db)):
    try:
        return {"ok": True, "promo": PromoOfferService.validate_public(db, code)}
    except PromoOfferError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/promo/redeem")
def redeem_promo_authenticated(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(get_current_principal),
):
    code = str(payload.get("promo_code") or payload.get("code") or "").strip()
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="promo_code required")
    try:
        row = PromoOfferService.redeem_for_org(
            db,
            org_id=principal.org_id,
            user_id=principal.user_id,
            promo_code=code,
            source="dashboard",
        )
    except PromoOfferError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    public = PromoOfferService.to_public_dict(row, db)
    return {
        "ok": True,
        "promo": public,
        "benefit_summary": public["benefit_summary"],
    }


@router.get("/admin/promo-offers")
def admin_list_promo_offers(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    rows = PromoOfferService.list_all(db)
    return [PromoOfferService.to_admin_dict(row, db) for row in rows]


@router.get("/admin/promo-offers/{promo_id}")
def admin_get_promo_offer(
    promo_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    row = db.get(PromoOffer, promo_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promo not found")
    return PromoOfferService.to_admin_dict(row, db)


@router.post("/admin/promo-offers")
def admin_create_promo_offer(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    try:
        row = PromoOfferService.create_admin(db, payload)
    except PromoOfferError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {"ok": True, "promo": PromoOfferService.to_admin_dict(row, db)}


@router.post("/admin/promo-offers/{promo_id}/apply")
def admin_apply_promo_to_orgs(
    promo_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    admin=Depends(require_platform_admin),
):
    org_ids = payload.get("org_ids") or []
    if not isinstance(org_ids, list) or not org_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="org_ids required")
    try:
        result = PromoOfferService.apply_to_orgs(
            db,
            promo_id=promo_id,
            org_ids=[str(x) for x in org_ids],
            actor_user_id=getattr(admin, "id", None) or getattr(admin, "user_id", None),
        )
    except PromoOfferError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return result


@router.patch("/admin/promo-offers/{promo_id}")
def admin_update_promo_offer(
    promo_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    try:
        row = PromoOfferService.update_admin(db, promo_id, payload)
    except PromoOfferError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {"ok": True, "promo": PromoOfferService.to_admin_dict(row, db)}
