from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.core.auth import (
    DriverPrincipal,
    RestaurantPrincipal,
    authenticate_driver,
    authenticate_restaurant,
    create_abuu_token,
    require_driver_user,
    require_restaurant_user,
)
from app.abuu.models.entities import (
    CustomerAddress,
    CustomerOrder,
    CustomerProfile,
    DeliveryAssignment,
    Driver,
    OrderEvent,
    Restaurant,
    RestaurantMenuCategory,
    RestaurantMenuItem,
)
from app.abuu.services.menu_service import AbuuMenuService
from app.abuu.services.order_service import AbuuOrderService
from app.abuu.services.location_service import find_nearest_restaurants
from app.abuu.services.serializers import (
    address_to_dict,
    assignment_to_dict,
    customer_to_dict,
    driver_to_dict,
    event_to_dict,
    menu_category_to_dict,
    menu_item_to_dict,
    order_to_dict,
    restaurant_to_dict,
)
from app.core.abuu_database import get_abuu_db
from app.core.admin_rbac import CAP_ABUU, require_cap
from app.core.security import hash_password
from app.models.user import User

router = APIRouter(prefix="/admin/abuu", tags=["abuu-admin"])


def _not_deleted(model):
    return model.is_deleted.is_(False)


@router.get("/restaurants")
def list_restaurants(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    is_available: bool | None = None,
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
):
    stmt = select(Restaurant).where(_not_deleted(Restaurant)).order_by(Restaurant.created_at.desc())
    if is_available is not None:
        stmt = stmt.where(Restaurant.is_available.is_(is_available))
    rows = db.execute(stmt.offset(offset).limit(limit)).scalars().all()
    return [restaurant_to_dict(r) for r in rows]


@router.get("/restaurants/nearest")
def nearest_restaurants(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
):
    ranked = find_nearest_restaurants(db, lat=lat, lng=lng, limit=limit)
    return [
        {
            **restaurant_to_dict(row.restaurant),
            "distance_km": round(row.distance_km, 3),
        }
        for row in ranked
    ]


@router.post("/restaurants")
def create_restaurant(payload: dict, db: Session = Depends(get_abuu_db), _admin: User = Depends(require_cap(CAP_ABUU))):
    row = Restaurant(
        name_en=str(payload.get("name_en") or "").strip(),
        name_ar=str(payload.get("name_ar") or "").strip(),
        status=str(payload.get("status") or "active"),
        is_available=bool(payload.get("is_available", True)),
        delivery_radius_km=float(payload.get("delivery_radius_km") or 5.0),
        latitude=payload.get("latitude"),
        longitude=payload.get("longitude"),
        address_text=payload.get("address_text"),
        phone=payload.get("phone"),
        login_email=(str(payload["login_email"]).strip().lower() if payload.get("login_email") else None),
    )
    if payload.get("password"):
        row.password_hash = hash_password(str(payload["password"]))
    if not row.name_en or not row.name_ar:
        raise HTTPException(status_code=400, detail="name_en and name_ar are required")
    db.add(row)
    db.commit()
    db.refresh(row)
    return restaurant_to_dict(row)


@router.get("/restaurants/{restaurant_id}")
def get_restaurant(restaurant_id: str, db: Session = Depends(get_abuu_db), _admin: User = Depends(require_cap(CAP_ABUU))):
    row = db.get(Restaurant, restaurant_id)
    if row is None or row.is_deleted:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return restaurant_to_dict(row)


@router.patch("/restaurants/{restaurant_id}")
def patch_restaurant(
    restaurant_id: str,
    payload: dict,
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
):
    row = db.get(Restaurant, restaurant_id)
    if row is None or row.is_deleted:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    for key in ("name_en", "name_ar", "status", "address_text", "phone", "login_email"):
        if key in payload:
            val = payload[key]
            if key == "login_email" and val:
                val = str(val).strip().lower()
            elif val is not None and key != "login_email":
                val = str(val).strip()
            setattr(row, key, val)
    for key in ("is_available",):
        if key in payload:
            setattr(row, key, bool(payload[key]))
    if "delivery_radius_km" in payload:
        row.delivery_radius_km = float(payload["delivery_radius_km"])
    if "latitude" in payload:
        row.latitude = payload["latitude"]
    if "longitude" in payload:
        row.longitude = payload["longitude"]
    if payload.get("password"):
        row.password_hash = hash_password(str(payload["password"]))
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return restaurant_to_dict(row)


@router.delete("/restaurants/{restaurant_id}")
def delete_restaurant(
    restaurant_id: str,
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
):
    row = db.get(Restaurant, restaurant_id)
    if row is None or row.is_deleted:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    row.is_deleted = True
    row.deleted_at = datetime.utcnow()
    db.add(row)
    db.commit()
    return {"ok": True}


@router.get("/restaurants/{restaurant_id}/menu")
def admin_restaurant_menu(
    restaurant_id: str,
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
):
    row = db.get(Restaurant, restaurant_id)
    if row is None or row.is_deleted:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return AbuuMenuService.nested_menu(db, restaurant_id)


@router.get("/restaurants/{restaurant_id}/menu-categories")
def list_menu_categories(
    restaurant_id: str,
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
):
    rows = db.execute(
        select(RestaurantMenuCategory)
        .where(RestaurantMenuCategory.restaurant_id == restaurant_id, _not_deleted(RestaurantMenuCategory))
        .order_by(RestaurantMenuCategory.sort_order.asc())
    ).scalars().all()
    return [menu_category_to_dict(r) for r in rows]


@router.post("/restaurants/{restaurant_id}/menu-categories")
def create_menu_category(
    restaurant_id: str,
    payload: dict,
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
):
    row = RestaurantMenuCategory(
        restaurant_id=restaurant_id,
        parent_category_id=payload.get("parent_category_id"),
        name_en=str(payload.get("name_en") or "").strip(),
        name_ar=str(payload.get("name_ar") or "").strip(),
        sort_order=int(payload.get("sort_order") or 100),
        is_available=bool(payload.get("is_available", True)),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return menu_category_to_dict(row)


@router.patch("/menu-categories/{category_id}")
def patch_menu_category(
    category_id: str,
    payload: dict,
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
):
    row = db.get(RestaurantMenuCategory, category_id)
    if row is None or row.is_deleted:
        raise HTTPException(status_code=404, detail="Category not found")
    AbuuMenuService.patch_category(db, row, payload)
    db.commit()
    db.refresh(row)
    return menu_category_to_dict(row)


@router.delete("/menu-categories/{category_id}")
def delete_menu_category(
    category_id: str,
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
):
    row = db.get(RestaurantMenuCategory, category_id)
    if row is None or row.is_deleted:
        raise HTTPException(status_code=404, detail="Category not found")
    AbuuMenuService.delete_category(db, row)
    db.commit()
    return {"ok": True}


@router.post("/menu-categories/{category_id}/items")
def create_menu_item(
    category_id: str,
    payload: dict,
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
):
    row = RestaurantMenuItem(
        category_id=category_id,
        name_en=str(payload.get("name_en") or "").strip(),
        name_ar=str(payload.get("name_ar") or "").strip(),
        description_en=payload.get("description_en"),
        description_ar=payload.get("description_ar"),
        item_type=str(payload.get("item_type") or "meat"),
        price_agorot=int(payload.get("price_agorot") or 0),
        parent_menu_item_id=payload.get("parent_menu_item_id"),
        is_available=bool(payload.get("is_available", True)),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return menu_item_to_dict(row)


@router.patch("/menu-items/{item_id}")
def patch_menu_item(
    item_id: str,
    payload: dict,
    db: Session = Depends(get_abuu_db),
    admin: User = Depends(require_cap(CAP_ABUU)),
):
    row = db.get(RestaurantMenuItem, item_id)
    if row is None or row.is_deleted:
        raise HTTPException(status_code=404, detail="Item not found")
    cat = db.get(RestaurantMenuCategory, row.category_id)
    AbuuMenuService.patch_item(
        db,
        row,
        payload,
        restaurant_id=cat.restaurant_id if cat else None,
        actor_type="admin",
        actor_id=admin.id,
    )
    db.commit()
    db.refresh(row)
    return menu_item_to_dict(row)


@router.delete("/menu-items/{item_id}")
def delete_menu_item(
    item_id: str,
    db: Session = Depends(get_abuu_db),
    admin: User = Depends(require_cap(CAP_ABUU)),
):
    row = db.get(RestaurantMenuItem, item_id)
    if row is None or row.is_deleted:
        raise HTTPException(status_code=404, detail="Item not found")
    cat = db.get(RestaurantMenuCategory, row.category_id)
    AbuuMenuService.delete_item(
        db,
        row,
        restaurant_id=cat.restaurant_id if cat else None,
        actor_type="admin",
        actor_id=admin.id,
    )
    db.commit()
    return {"ok": True}


@router.post("/menu-items/{item_id}/photo")
async def upload_menu_item_photo(
    item_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
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
    if cat is None:
        raise HTTPException(status_code=404, detail="Category not found")
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


@router.get("/drivers")
def list_drivers(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
):
    rows = db.execute(select(Driver).where(_not_deleted(Driver)).offset(offset).limit(limit)).scalars().all()
    return [driver_to_dict(r) for r in rows]


@router.post("/drivers")
def create_driver(payload: dict, db: Session = Depends(get_abuu_db), _admin: User = Depends(require_cap(CAP_ABUU))):
    row = Driver(
        name=str(payload.get("name") or "").strip(),
        phone=payload.get("phone"),
        status=str(payload.get("status") or "active"),
        is_available=bool(payload.get("is_available", True)),
        latitude=payload.get("latitude"),
        longitude=payload.get("longitude"),
        vehicle_info=payload.get("vehicle_info"),
        login_email=(str(payload["login_email"]).strip().lower() if payload.get("login_email") else None),
    )
    if payload.get("password"):
        row.password_hash = hash_password(str(payload["password"]))
    db.add(row)
    db.commit()
    db.refresh(row)
    return driver_to_dict(row)


@router.get("/drivers/{driver_id}")
def get_driver(driver_id: str, db: Session = Depends(get_abuu_db), _admin: User = Depends(require_cap(CAP_ABUU))):
    row = db.get(Driver, driver_id)
    if row is None or row.is_deleted:
        raise HTTPException(status_code=404, detail="Driver not found")
    return driver_to_dict(row)


@router.patch("/drivers/{driver_id}")
def patch_driver(
    driver_id: str,
    payload: dict,
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
):
    row = db.get(Driver, driver_id)
    if row is None or row.is_deleted:
        raise HTTPException(status_code=404, detail="Driver not found")
    for key in ("name", "phone", "status", "vehicle_info", "login_email"):
        if key in payload:
            val = payload[key]
            if key == "login_email" and val:
                val = str(val).strip().lower()
            setattr(row, key, val)
    for key in ("is_available",):
        if key in payload:
            setattr(row, key, bool(payload[key]))
    if "latitude" in payload:
        row.latitude = payload["latitude"]
    if "longitude" in payload:
        row.longitude = payload["longitude"]
    if payload.get("password"):
        row.password_hash = hash_password(str(payload["password"]))
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return driver_to_dict(row)


@router.delete("/drivers/{driver_id}")
def delete_driver(driver_id: str, db: Session = Depends(get_abuu_db), _admin: User = Depends(require_cap(CAP_ABUU))):
    row = db.get(Driver, driver_id)
    if row is None or row.is_deleted:
        raise HTTPException(status_code=404, detail="Driver not found")
    row.is_deleted = True
    row.deleted_at = datetime.utcnow()
    row.is_available = False
    db.add(row)
    db.commit()
    return {"ok": True}


@router.get("/customers")
def list_customers(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
):
    rows = db.execute(select(CustomerProfile).where(_not_deleted(CustomerProfile)).offset(offset).limit(limit)).scalars().all()
    return [customer_to_dict(r) for r in rows]


@router.get("/customers/{customer_id}")
def get_customer(customer_id: str, db: Session = Depends(get_abuu_db), _admin: User = Depends(require_cap(CAP_ABUU))):
    row = db.get(CustomerProfile, customer_id)
    if row is None or row.is_deleted:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer_to_dict(row)


@router.get("/customers/{customer_id}/history")
def customer_history(customer_id: str, db: Session = Depends(get_abuu_db), _admin: User = Depends(require_cap(CAP_ABUU))):
    customer = db.get(CustomerProfile, customer_id)
    if customer is None or customer.is_deleted:
        raise HTTPException(status_code=404, detail="Customer not found")
    orders = db.execute(
        select(CustomerOrder).where(CustomerOrder.customer_id == customer_id, _not_deleted(CustomerOrder))
    ).scalars().all()
    return {
        "customer": customer_to_dict(customer),
        "orders": [AbuuOrderService.get_order_detail(db, o.id) for o in orders],
    }


@router.get("/customers/{customer_id}/addresses")
def list_addresses(customer_id: str, db: Session = Depends(get_abuu_db), _admin: User = Depends(require_cap(CAP_ABUU))):
    rows = db.execute(
        select(CustomerAddress).where(CustomerAddress.customer_id == customer_id, _not_deleted(CustomerAddress))
    ).scalars().all()
    return [address_to_dict(r) for r in rows]


@router.get("/orders")
def list_orders(
    restaurant_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
):
    stmt = select(CustomerOrder).where(_not_deleted(CustomerOrder)).order_by(CustomerOrder.created_at.desc())
    if restaurant_id:
        stmt = stmt.where(CustomerOrder.restaurant_id == restaurant_id)
    if status:
        stmt = stmt.where(CustomerOrder.status == status)
    rows = db.execute(stmt.offset(offset).limit(limit)).scalars().all()
    return [order_to_dict(r) for r in rows]


@router.get("/orders/{order_id}")
def get_order(order_id: str, db: Session = Depends(get_abuu_db), _admin: User = Depends(require_cap(CAP_ABUU))):
    detail = AbuuOrderService.get_order_detail(db, order_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return detail


@router.patch("/orders/{order_id}/status")
def patch_order_status(
    order_id: str,
    payload: dict,
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
):
    order = db.get(CustomerOrder, order_id)
    if order is None or order.is_deleted:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        AbuuOrderService.patch_status(db, order, str(payload.get("status") or ""))
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AbuuOrderService.get_order_detail(db, order_id)


@router.post("/orders/{order_id}/mark-paid")
def mark_order_paid(
    order_id: str,
    db: Session = Depends(get_abuu_db),
    admin: User = Depends(require_cap(CAP_ABUU)),
):
    order = db.get(CustomerOrder, order_id)
    if order is None or order.is_deleted:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        AbuuOrderService.mark_paid_manual(db, order, confirmed_by=admin.email or admin.id)
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AbuuOrderService.get_order_detail(db, order_id)


@router.get("/orders/{order_id}/events")
def list_order_events(order_id: str, db: Session = Depends(get_abuu_db), _admin: User = Depends(require_cap(CAP_ABUU))):
    rows = db.execute(select(OrderEvent).where(OrderEvent.order_id == order_id).order_by(OrderEvent.created_at.asc())).scalars().all()
    return [event_to_dict(r) for r in rows]


@router.post("/orders/{order_id}/assignments")
def create_assignment(
    order_id: str,
    payload: dict,
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
):
    existing = db.execute(select(DeliveryAssignment).where(DeliveryAssignment.order_id == order_id)).scalars().first()
    if existing:
        raise HTTPException(status_code=409, detail="Assignment already exists")
    order = db.get(CustomerOrder, order_id)
    if order is None or order.is_deleted:
        raise HTTPException(status_code=404, detail="Order not found")
    driver_id = payload.get("driver_id")
    row = DeliveryAssignment(
        order_id=order_id,
        driver_id=driver_id,
        status="assigned" if driver_id else "unassigned",
        assigned_at=datetime.utcnow() if driver_id else None,
    )
    db.add(row)
    if driver_id and order.status == "ready":
        AbuuOrderService.patch_status(db, order, "assigned_to_driver")
    db.commit()
    db.refresh(row)
    return assignment_to_dict(row)


@router.get("/events")
def list_external_events(
    status: str | None = None,
    event_type: str | None = None,
    order_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
):
    from app.abuu.services.event_idempotency_service import AbuuEventIdempotencyService
    from app.abuu.services.serializers import external_event_to_dict

    rows = AbuuEventIdempotencyService.list_events(
        db,
        status=status,
        event_type=event_type,
        order_id=order_id,
        limit=limit,
        offset=offset,
    )
    return [external_event_to_dict(r) for r in rows]


@router.post("/orders/{order_id}/cancel-paid")
def cancel_paid_order(
    order_id: str,
    payload: dict,
    db: Session = Depends(get_abuu_db),
    admin: User = Depends(require_cap(CAP_ABUU)),
):
    order = db.get(CustomerOrder, order_id)
    if order is None or order.is_deleted:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        AbuuOrderService.cancel_paid_order(
            db,
            order,
            reason=str(payload.get("reason") or ""),
            actor=admin.email or admin.id,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AbuuOrderService.get_order_detail(db, order_id)


@router.post("/orders/{order_id}/refund-processed")
def mark_refund_processed(
    order_id: str,
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
):
    order = db.get(CustomerOrder, order_id)
    if order is None or order.is_deleted:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        AbuuOrderService.mark_refund_processed(db, order)
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AbuuOrderService.get_order_detail(db, order_id)


@router.post("/orders/{order_id}/recover")
def recover_order(
    order_id: str,
    payload: dict,
    db: Session = Depends(get_abuu_db),
    admin: User = Depends(require_cap(CAP_ABUU)),
):
    order = db.get(CustomerOrder, order_id)
    if order is None or order.is_deleted:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        AbuuOrderService.admin_recover(
            db,
            order,
            action=str(payload.get("action") or ""),
            note=payload.get("note"),
            actor=admin.email or admin.id,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AbuuOrderService.get_order_detail(db, order_id)


@router.post("/assignments/{assignment_id}/timeout")
def timeout_assignment(
    assignment_id: str,
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
):
    row = db.get(DeliveryAssignment, assignment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    try:
        AbuuOrderService.assignment_timeout(db, row)
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return assignment_to_dict(row)


@router.get("/agent-settings")
def get_agent_settings(db: Session = Depends(get_abuu_db), _admin: User = Depends(require_cap(CAP_ABUU))):
    from app.abuu.services.agent_settings_service import agent_settings_to_dict, get_skills_config
    from app.abuu.services.kb_service import get_global_settings
    from app.abuu.services.skill_definitions import SKILL_DESCRIPTIONS

    row = get_global_settings(db)
    return {
        "settings": agent_settings_to_dict(row),
        "skills": [
            {"name": name, "description": SKILL_DESCRIPTIONS.get(name, ""), "enabled": cfg.get("enabled", True)}
            for name, cfg in get_skills_config(db).items()
        ],
    }


@router.patch("/agent-settings")
def patch_agent_settings(payload: dict, db: Session = Depends(get_abuu_db), _admin: User = Depends(require_cap(CAP_ABUU))):
    from app.abuu.services.agent_settings_service import agent_settings_to_dict, patch_global_settings

    row = patch_global_settings(db, payload)
    db.commit()
    db.refresh(row)
    return agent_settings_to_dict(row)


@router.get("/restaurants/{restaurant_id}/agent-settings")
def get_restaurant_agent_settings(
    restaurant_id: str,
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
):
    from app.abuu.services.agent_settings_service import restaurant_settings_to_dict
    from app.abuu.services.kb_service import get_restaurant_settings, resolve_settings

    row = get_restaurant_settings(db, restaurant_id)
    resolved = resolve_settings(db, restaurant_id=restaurant_id)
    return {
        "override": restaurant_settings_to_dict(row) if row else None,
        "resolved": {
            "delivery_radius_km": resolved.delivery_radius_km,
            "prep_minutes": resolved.prep_minutes,
            "min_order_agorot": resolved.min_order_agorot,
            "delivery_fee_agorot": resolved.delivery_fee_agorot,
            "greeting_template_en": resolved.greeting_template_en,
            "greeting_template_ar": resolved.greeting_template_ar,
        },
    }


@router.patch("/restaurants/{restaurant_id}/agent-settings")
def patch_restaurant_agent_settings(
    restaurant_id: str,
    payload: dict,
    db: Session = Depends(get_abuu_db),
    _admin: User = Depends(require_cap(CAP_ABUU)),
):
    from app.abuu.services.agent_settings_service import patch_restaurant_settings, restaurant_settings_to_dict

    if db.get(Restaurant, restaurant_id) is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    row = patch_restaurant_settings(db, restaurant_id, payload)
    db.commit()
    db.refresh(row)
    return restaurant_settings_to_dict(row)
