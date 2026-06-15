from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.core.auth import RestaurantPrincipal, require_restaurant_user
from app.abuu.models.entities import CustomerOrder, CustomerProfile, Restaurant, RestaurantMenuCategory, RestaurantMenuItem, RestaurantPromoOffer
from app.abuu.services.inbound_service import AbuuInboundService
from app.abuu.services.menu_service import AbuuMenuService
from app.abuu.services.notification_service import AbuuNotificationService
from app.abuu.services.offer_service import AbuuOfferService, offer_to_dict
from app.abuu.services.order_service import AbuuOrderService
from app.abuu.services.order_substitution_service import AbuuOrderSubstitutionService
from app.abuu.services.reply_service import item_unavailable_message
from app.abuu.services.serializers import menu_category_to_dict, menu_item_to_dict, notification_to_dict, order_to_dict, restaurant_to_dict
from app.core.abuu_database import get_abuu_db
from app.core.database import get_db

router = APIRouter(prefix="/abuu/restaurant", tags=["abuu-restaurant"])

RESTAURANT_BOARD_STATUSES = {
    "new": {"sent_to_restaurant"},
    "preparing": {"preparing"},
    "ready": {"ready"},
    "cancelled": {"cancelled"},
    "completed": {"delivered"},
}


@router.get("/me")
def restaurant_me(
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    db: Session = Depends(get_abuu_db),
):
    row = db.get(Restaurant, principal.restaurant_id)
    return restaurant_to_dict(row)


@router.get("/menu")
def restaurant_menu(
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    db: Session = Depends(get_abuu_db),
):
    return AbuuMenuService.nested_menu(db, principal.restaurant_id)


@router.post("/menu/categories")
def create_menu_category(
    payload: dict,
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    db: Session = Depends(get_abuu_db),
):
    row = AbuuMenuService.create_category(
        db,
        restaurant_id=principal.restaurant_id,
        name_en=str(payload.get("name_en") or ""),
        name_ar=str(payload.get("name_ar") or ""),
        sort_order=int(payload.get("sort_order") or 100),
        is_available=bool(payload.get("is_available", True)),
        parent_category_id=payload.get("parent_category_id"),
    )
    db.commit()
    db.refresh(row)
    return menu_category_to_dict(row)


@router.patch("/menu/categories/{category_id}")
def patch_menu_category(
    category_id: str,
    payload: dict,
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    db: Session = Depends(get_abuu_db),
):
    row = db.get(RestaurantMenuCategory, category_id)
    if row is None or row.is_deleted or row.restaurant_id != principal.restaurant_id:
        raise HTTPException(status_code=404, detail="Category not found")
    AbuuMenuService.patch_category(db, row, payload)
    db.commit()
    db.refresh(row)
    return menu_category_to_dict(row)


@router.delete("/menu/categories/{category_id}")
def delete_menu_category(
    category_id: str,
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    db: Session = Depends(get_abuu_db),
):
    row = db.get(RestaurantMenuCategory, category_id)
    if row is None or row.is_deleted or row.restaurant_id != principal.restaurant_id:
        raise HTTPException(status_code=404, detail="Category not found")
    AbuuMenuService.delete_category(db, row)
    db.commit()
    return {"ok": True}


@router.post("/menu/categories/{category_id}/items")
def create_menu_item(
    category_id: str,
    payload: dict,
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    db: Session = Depends(get_abuu_db),
):
    cat = db.get(RestaurantMenuCategory, category_id)
    if cat is None or cat.is_deleted or cat.restaurant_id != principal.restaurant_id:
        raise HTTPException(status_code=404, detail="Category not found")
    row = AbuuMenuService.create_item(
        db,
        category_id=category_id,
        name_en=str(payload.get("name_en") or ""),
        name_ar=str(payload.get("name_ar") or ""),
        item_type=str(payload.get("item_type") or "meat"),
        price_agorot=int(payload.get("price_agorot") or 0),
        description_en=payload.get("description_en"),
        description_ar=payload.get("description_ar"),
        parent_menu_item_id=payload.get("parent_menu_item_id"),
        is_available=bool(payload.get("is_available", True)),
    )
    db.commit()
    db.refresh(row)
    return menu_item_to_dict(row)


@router.patch("/menu/items/{item_id}")
def patch_menu_item(
    item_id: str,
    payload: dict,
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    db: Session = Depends(get_abuu_db),
):
    row = db.get(RestaurantMenuItem, item_id)
    if row is None or row.is_deleted:
        raise HTTPException(status_code=404, detail="Item not found")
    cat = db.get(RestaurantMenuCategory, row.category_id)
    if cat is None or cat.restaurant_id != principal.restaurant_id:
        raise HTTPException(status_code=404, detail="Item not found")
    AbuuMenuService.patch_item(
        db,
        row,
        payload,
        restaurant_id=principal.restaurant_id,
        actor_type="restaurant",
        actor_id=principal.restaurant_id,
    )
    db.commit()
    db.refresh(row)
    return menu_item_to_dict(row)


@router.delete("/menu/items/{item_id}")
def delete_menu_item(
    item_id: str,
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    db: Session = Depends(get_abuu_db),
):
    row = db.get(RestaurantMenuItem, item_id)
    if row is None or row.is_deleted:
        raise HTTPException(status_code=404, detail="Item not found")
    cat = db.get(RestaurantMenuCategory, row.category_id)
    if cat is None or cat.restaurant_id != principal.restaurant_id:
        raise HTTPException(status_code=404, detail="Item not found")
    AbuuMenuService.delete_item(
        db,
        row,
        restaurant_id=principal.restaurant_id,
        actor_type="restaurant",
        actor_id=principal.restaurant_id,
    )
    db.commit()
    return {"ok": True}


@router.get("/orders")
def restaurant_orders(
    board: str | None = Query(None),
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    db: Session = Depends(get_abuu_db),
):
    rows = db.execute(
        select(CustomerOrder)
        .where(
            CustomerOrder.restaurant_id == principal.restaurant_id,
            CustomerOrder.is_deleted.is_(False),
        )
        .order_by(CustomerOrder.created_at.desc())
    ).scalars().all()
    if board:
        allowed = RESTAURANT_BOARD_STATUSES.get(board.lower(), set())
        rows = [r for r in rows if r.status in allowed]
    return [order_to_dict(r) for r in rows]


@router.get("/orders/{order_id}")
def restaurant_order_detail(
    order_id: str,
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    db: Session = Depends(get_abuu_db),
):
    order = db.get(CustomerOrder, order_id)
    if order is None or order.is_deleted or order.restaurant_id != principal.restaurant_id:
        raise HTTPException(status_code=404, detail="Order not found")
    detail = AbuuOrderService.get_order_detail(db, order_id)
    return detail


@router.post("/orders/{order_id}/preparing")
def restaurant_start_preparing(
    order_id: str,
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    db: Session = Depends(get_abuu_db),
):
    order = db.get(CustomerOrder, order_id)
    if order is None or order.is_deleted or order.restaurant_id != principal.restaurant_id:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        AbuuOrderService.restaurant_start_preparing(db, order)
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AbuuOrderService.get_order_detail(db, order_id)


@router.post("/orders/{order_id}/ready")
def restaurant_mark_ready(
    order_id: str,
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    db: Session = Depends(get_abuu_db),
):
    order = db.get(CustomerOrder, order_id)
    if order is None or order.is_deleted or order.restaurant_id != principal.restaurant_id:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        AbuuOrderService.restaurant_mark_ready(db, order)
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AbuuOrderService.get_order_detail(db, order_id)


@router.post("/orders/{order_id}/items/{item_id}/unavailable")
def restaurant_mark_item_unavailable(
    order_id: str,
    item_id: str,
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    abuu_db: Session = Depends(get_abuu_db),
    main_db: Session = Depends(get_db),
):
    order = abuu_db.get(CustomerOrder, order_id)
    if order is None or order.is_deleted or order.restaurant_id != principal.restaurant_id:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        line = AbuuOrderSubstitutionService.mark_line_unavailable(
            abuu_db,
            order=order,
            line_id=item_id,
            restaurant_id=principal.restaurant_id,
        )
        customer = abuu_db.get(CustomerProfile, order.customer_id)
        if customer and customer.phone:
            lang = customer.preferred_language or "ar"
            item_name = line.name_ar if lang == "ar" else (line.name_en or line.name_ar or "item")
            try:
                AbuuInboundService._send_reply(
                    main_db,
                    customer.phone,
                    item_unavailable_message(item_name, lang),
                    org_id=None,
                )
            except Exception:
                pass
            AbuuOrderSubstitutionService.setup_substitution_session(
                abuu_db,
                phone=customer.phone,
                order_id=order.id,
                pending_line_id=line.id,
            )
        abuu_db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AbuuOrderService.get_order_detail(abuu_db, order_id)


@router.post("/orders/{order_id}/items/{item_id}/available")
def restaurant_undo_item_unavailable(
    order_id: str,
    item_id: str,
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    db: Session = Depends(get_abuu_db),
):
    order = db.get(CustomerOrder, order_id)
    if order is None or order.is_deleted or order.restaurant_id != principal.restaurant_id:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        AbuuOrderSubstitutionService.undo_line_unavailable(
            db,
            order=order,
            line_id=item_id,
            restaurant_id=principal.restaurant_id,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AbuuOrderService.get_order_detail(db, order_id)


@router.patch("/orders/{order_id}/prep-delay")
def restaurant_prep_delay(
    order_id: str,
    payload: dict,
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    db: Session = Depends(get_abuu_db),
):
    order = db.get(CustomerOrder, order_id)
    if order is None or order.is_deleted or order.restaurant_id != principal.restaurant_id:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        AbuuOrderService.set_prep_delay_note(db, order, str(payload.get("note") or ""))
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AbuuOrderService.get_order_detail(db, order_id)


@router.post("/menu/items/{item_id}/photo")
async def upload_menu_item_photo(
    item_id: str,
    file: UploadFile = File(...),
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    db: Session = Depends(get_abuu_db),
):
    from app.abuu.services.abuu_menu_photo_storage_service import (
        delete_photo_file,
        save_photo_bytes,
        storage_key_for,
        validate_menu_photo_upload,
    )

    row = db.get(RestaurantMenuItem, item_id)
    if row is None or row.is_deleted:
        raise HTTPException(status_code=404, detail="Item not found")
    cat = db.get(RestaurantMenuCategory, row.category_id)
    if cat is None or cat.restaurant_id != principal.restaurant_id:
        raise HTTPException(status_code=404, detail="Item not found")
    content = await file.read()
    try:
        ext = validate_menu_photo_upload(filename=file.filename or "photo.jpg", content=content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    delete_photo_file(row.photo_storage_key)
    key = storage_key_for(restaurant_id=cat.restaurant_id, item_id=row.id, ext=ext)
    try:
        save_photo_bytes(storage_key=key, content=content)
    except Exception as exc:
        from app.abuu.services.abuu_menu_photo_storage_service import MenuPhotoStorageError

        if isinstance(exc, MenuPhotoStorageError):
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        raise
    row.photo_storage_key = key
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return menu_item_to_dict(row)


@router.get("/notifications")
def restaurant_notifications(
    unread_only: bool = False,
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    db: Session = Depends(get_abuu_db),
):
    rows = AbuuNotificationService.list_for_target(
        db,
        target_type="restaurant",
        target_id=principal.restaurant_id,
        unread_only=unread_only,
    )
    return [notification_to_dict(r) for r in rows]


@router.patch("/notifications/{notification_id}/read")
def restaurant_mark_notification_read(
    notification_id: str,
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    db: Session = Depends(get_abuu_db),
):
    row = AbuuNotificationService.mark_read(
        db,
        notification_id,
        target_type="restaurant",
        target_id=principal.restaurant_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    db.commit()
    return notification_to_dict(row)


@router.get("/offers")
def restaurant_offers(
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    db: Session = Depends(get_abuu_db),
):
    rows = AbuuOfferService.list_for_restaurant(db, principal.restaurant_id, active_only=False)
    return [offer_to_dict(row) for row in rows]


@router.post("/offers")
def create_restaurant_offer(
    payload: dict,
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    db: Session = Depends(get_abuu_db),
):
    row = AbuuOfferService.create(
        db,
        restaurant_id=principal.restaurant_id,
        title_en=str(payload.get("title_en") or ""),
        title_ar=str(payload.get("title_ar") or ""),
        offer_price_agorot=int(payload.get("offer_price_agorot") or 0),
        original_price_agorot=int(payload.get("original_price_agorot") or 0),
        items=payload.get("items") if isinstance(payload.get("items"), list) else [],
        tags=payload.get("tags") if isinstance(payload.get("tags"), list) else [],
        description_en=payload.get("description_en"),
        description_ar=payload.get("description_ar"),
        is_active=bool(payload.get("is_active", True)),
    )
    db.commit()
    db.refresh(row)
    return offer_to_dict(row)


@router.patch("/offers/{offer_id}")
def patch_restaurant_offer(
    offer_id: str,
    payload: dict,
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    db: Session = Depends(get_abuu_db),
):
    row = db.get(RestaurantPromoOffer, offer_id)
    if row is None or row.is_deleted or row.restaurant_id != principal.restaurant_id:
        raise HTTPException(status_code=404, detail="Offer not found")
    AbuuOfferService.patch(db, row, payload)
    db.commit()
    db.refresh(row)
    return offer_to_dict(row)


@router.delete("/offers/{offer_id}")
def delete_restaurant_offer(
    offer_id: str,
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
    db: Session = Depends(get_abuu_db),
):
    row = db.get(RestaurantPromoOffer, offer_id)
    if row is None or row.is_deleted or row.restaurant_id != principal.restaurant_id:
        raise HTTPException(status_code=404, detail="Offer not found")
    AbuuOfferService.delete(db, row)
    db.commit()
    return {"ok": True}
