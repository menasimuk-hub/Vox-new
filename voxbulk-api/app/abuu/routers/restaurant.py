from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.core.auth import RestaurantPrincipal, require_restaurant_user
from app.abuu.models.entities import CustomerOrder, Restaurant, RestaurantMenuCategory, RestaurantMenuItem
from app.abuu.services.serializers import menu_category_to_dict, menu_item_to_dict, order_to_dict, restaurant_to_dict
from app.core.abuu_database import get_abuu_db

router = APIRouter(prefix="/abuu/restaurant", tags=["abuu-restaurant"])


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
    categories = db.execute(
        select(RestaurantMenuCategory)
        .where(
            RestaurantMenuCategory.restaurant_id == principal.restaurant_id,
            RestaurantMenuCategory.is_deleted.is_(False),
        )
        .order_by(RestaurantMenuCategory.sort_order.asc())
    ).scalars().all()
    out = []
    for cat in categories:
        items = db.execute(
            select(RestaurantMenuItem).where(
                RestaurantMenuItem.category_id == cat.id,
                RestaurantMenuItem.is_deleted.is_(False),
            )
        ).scalars().all()
        out.append({**menu_category_to_dict(cat), "items": [menu_item_to_dict(i) for i in items]})
    return out


@router.get("/orders")
def restaurant_orders(
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
    return [order_to_dict(r) for r in rows]
