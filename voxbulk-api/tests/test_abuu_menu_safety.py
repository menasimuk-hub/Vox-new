from __future__ import annotations

import uuid

from sqlalchemy import select

from app.abuu.models.entities import AbuuMenuAuditLog, CustomerOrder, CustomerOrderItem, CustomerProfile, Restaurant, RestaurantMenuItem
from app.core.abuu_database import get_abuu_sessionmaker, run_abuu_migrations
from tests.test_abuu_crud import _mk_superadmin


def test_menu_edit_after_paid_keeps_line_snapshot(app_client):
    run_abuu_migrations()
    headers = _mk_superadmin(app_client)

    with get_abuu_sessionmaker()() as db:
        restaurant = db.execute(select(Restaurant).limit(1)).scalar_one()
        item = db.execute(select(RestaurantMenuItem).limit(1)).scalar_one()
        original_name = item.name_en
        customer = CustomerProfile(phone=f"+97257{uuid.uuid4().int % 10_000_000:07d}", preferred_language="ar")
        db.add(customer)
        db.flush()
        order = CustomerOrder(
            customer_id=customer.id,
            restaurant_id=restaurant.id,
            status="confirmed",
            payment_status="pending_manual",
            total_agorot=item.price_agorot,
        )
        db.add(order)
        db.flush()
        db.add(
            CustomerOrderItem(
                order_id=order.id,
                menu_item_id=item.id,
                name_en=item.name_en,
                name_ar=item.name_ar,
                item_type=item.item_type,
                quantity=1,
                unit_price_agorot=item.price_agorot,
                line_total_agorot=item.price_agorot,
            )
        )
        db.commit()
        order_id = order.id
        item_id = item.id

    app_client.post(f"/admin/abuu/orders/{order_id}/mark-paid", headers=headers)
    app_client.patch(
        f"/admin/abuu/menu-items/{item_id}",
        headers=headers,
        json={"name_en": "Renamed Item", "price_agorot": 9999},
    )

    detail = app_client.get(f"/admin/abuu/orders/{order_id}", headers=headers).json()
    assert detail["items"][0]["name_en"] == original_name
    assert detail["items"][0]["unit_price_agorot"] != 9999

    with get_abuu_sessionmaker()() as db:
        audits = db.execute(
            select(AbuuMenuAuditLog).where(AbuuMenuAuditLog.menu_item_id == item_id)
        ).scalars().all()
    assert len(audits) >= 1
