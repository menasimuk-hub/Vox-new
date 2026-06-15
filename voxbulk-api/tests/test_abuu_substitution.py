from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.abuu_database import get_abuu_sessionmaker, run_abuu_migrations
from app.core.config import get_settings
from app.core.security import hash_password
from app.abuu.models.entities import (
    CustomerOrder,
    CustomerOrderItem,
    CustomerProfile,
    Restaurant,
    RestaurantMenuItem,
)
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.order_service import AbuuOrderService


def test_yallasay_auto_send_on_confirm(app_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "yallasay_auto_send_on_confirm", True)
    run_abuu_migrations()

    with get_abuu_sessionmaker()() as db:
        restaurant = db.execute(select(Restaurant).limit(1)).scalar_one()
        restaurant.login_email = f"auto_{uuid.uuid4().hex[:6]}@abuu.test"
        restaurant.password_hash = hash_password("pass123")
        customer = CustomerProfile(phone="+972506666666", preferred_language="ar", name="Auto Customer")
        db.add(customer)
        db.flush()
        item = db.execute(select(RestaurantMenuItem).limit(1)).scalar_one()
        order = CustomerOrder(
            customer_id=customer.id,
            restaurant_id=restaurant.id,
            status="draft",
            payment_status="unpaid",
            total_agorot=2500,
        )
        db.add(order)
        db.flush()
        db.add(
            CustomerOrderItem(
                order_id=order.id,
                menu_item_id=item.id,
                name_en=item.name_en,
                name_ar=item.name_ar,
                quantity=1,
                unit_price_agorot=2500,
                line_total_agorot=2500,
            )
        )
        db.commit()
        order_id = order.id
        rest_email = restaurant.login_email

    with get_abuu_sessionmaker()() as db:
        order = db.get(CustomerOrder, order_id)
        AbuuOrderDraftService.confirm_draft(db, order)
        AbuuOrderService.mark_paid_manual(db, order, confirmed_by="yallasay_whatsapp")
        db.commit()
        assert order.status == "sent_to_restaurant"

    rest_tok = app_client.post(
        "/abuu/auth/restaurant/token",
        data={"username": rest_email, "password": "pass123"},
    ).json()["access_token"]
    rows = app_client.get(
        "/abuu/restaurant/orders",
        headers={"Authorization": f"Bearer {rest_tok}"},
    ).json()
    assert any(r["id"] == order_id and r["status"] == "sent_to_restaurant" for r in rows)


def test_restaurant_mark_item_unavailable_blocks_ready(app_client):
    run_abuu_migrations()

    with get_abuu_sessionmaker()() as db:
        restaurant = db.execute(select(Restaurant).limit(1)).scalar_one()
        restaurant.login_email = f"oos_{uuid.uuid4().hex[:6]}@abuu.test"
        restaurant.password_hash = hash_password("pass123")
        customer = CustomerProfile(phone="+972507777778", preferred_language="en", name="OOS Customer")
        db.add(customer)
        db.flush()
        item = db.execute(select(RestaurantMenuItem).limit(1)).scalar_one()
        order = CustomerOrder(
            customer_id=customer.id,
            restaurant_id=restaurant.id,
            status="sent_to_restaurant",
            payment_status="paid_manual",
            total_agorot=3000,
        )
        db.add(order)
        db.flush()
        line = CustomerOrderItem(
            order_id=order.id,
            menu_item_id=item.id,
            name_en=item.name_en,
            name_ar=item.name_ar,
            quantity=1,
            unit_price_agorot=3000,
            line_total_agorot=3000,
        )
        db.add(line)
        db.commit()
        order_id = order.id
        line_id = line.id
        rest_email = restaurant.login_email

    rest_tok = app_client.post(
        "/abuu/auth/restaurant/token",
        data={"username": rest_email, "password": "pass123"},
    ).json()["access_token"]
    rest_headers = {"Authorization": f"Bearer {rest_tok}"}

    mark = app_client.post(
        f"/abuu/restaurant/orders/{order_id}/items/{line_id}/unavailable",
        headers=rest_headers,
        json={},
    )
    assert mark.status_code == 200
    assert mark.json()["substitution_pending"] is True

    prep = app_client.post(f"/abuu/restaurant/orders/{order_id}/preparing", headers=rest_headers, json={})
    assert prep.status_code == 200

    ready = app_client.post(f"/abuu/restaurant/orders/{order_id}/ready", headers=rest_headers, json={})
    assert ready.status_code == 400


def test_restaurant_start_preparing_from_confirmed(app_client):
    run_abuu_migrations()

    with get_abuu_sessionmaker()() as db:
        restaurant = db.execute(select(Restaurant).limit(1)).scalar_one()
        restaurant.login_email = f"prep_{uuid.uuid4().hex[:6]}@abuu.test"
        restaurant.password_hash = hash_password("pass123")
        customer = CustomerProfile(phone="+972507777779", preferred_language="en", name="Prep Customer")
        db.add(customer)
        db.flush()
        order = CustomerOrder(
            customer_id=customer.id,
            restaurant_id=restaurant.id,
            status="confirmed",
            payment_status="pending_manual",
            total_agorot=2500,
        )
        db.add(order)
        db.commit()
        order_id = order.id
        rest_email = restaurant.login_email

    rest_tok = app_client.post(
        "/abuu/auth/restaurant/token",
        data={"username": rest_email, "password": "pass123"},
    ).json()["access_token"]
    rest_headers = {"Authorization": f"Bearer {rest_tok}"}

    prep = app_client.post(f"/abuu/restaurant/orders/{order_id}/preparing", headers=rest_headers, json={})
    assert prep.status_code == 200
    assert prep.json()["status"] == "preparing"
    assert prep.json()["payment_status"] == "paid_manual"
