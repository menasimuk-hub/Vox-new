from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.admin_rbac import require_platform_admin
from app.core.database import get_db
from app.services.promo_offer_service import PromoOfferError, PromoOfferService

router = APIRouter(tags=["promo"])


@router.get("/promo/{code}")
def public_promo_preview(code: str, db: Session = Depends(get_db)):
    try:
        return {"ok": True, "promo": PromoOfferService.validate_public(db, code)}
    except PromoOfferError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.get("/admin/promo-offers")
def admin_list_promo_offers(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    rows = PromoOfferService.list_all(db)
    return [PromoOfferService.to_admin_dict(row) for row in rows]


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
    return {"ok": True, "promo": PromoOfferService.to_admin_dict(row)}


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
    return {"ok": True, "promo": PromoOfferService.to_admin_dict(row)}
