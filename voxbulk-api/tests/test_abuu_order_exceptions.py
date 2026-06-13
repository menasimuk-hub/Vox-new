from __future__ import annotations

import uuid

from sqlalchemy import select

from app.abuu.models.entities import CustomerOrder, CustomerProfile, Restaurant
from app.core.abuu_database import get_abuu_sessionmaker, run_abuu_migrations
from app.core.security import hash_password
from tests.test_abuu_crud import _mk_superadmin


def test_cancel_paid_and_prep_delay(app_client):
    run_abuu_migrations()
    headers = _mk_superadmin(app_client)

    with get_abuu_sessionmaker()() as db:
        restaurant = db.execute(select(Restaurant).limit(1)).scalar_one()
        restaurant.login_email = f"rest_exc_{uuid.uuid4().hex[:6]}@abuu.test"
        restaurant.password_hash = hash_password("pass123")
        customer = CustomerProfile(phone=f"+97255{uuid.uuid4().int % 10_000_000:07d}", preferred_language="ar")
        db.add(customer)
        db.flush()
        order = CustomerOrder(
            customer_id=customer.id,
            restaurant_id=restaurant.id,
            status="confirmed",
            payment_status="pending_manual",
            total_agorot=6000,
        )
        db.add(order)
        db.commit()
        order_id = order.id
        rest_email = restaurant.login_email

    app_client.post(f"/admin/abuu/orders/{order_id}/mark-paid", headers=headers)
    rest_tok = app_client.post(
        "/abuu/auth/restaurant/token",
        data={"username": rest_email, "password": "pass123"},
    ).json()["access_token"]
    rest_headers = {"Authorization": f"Bearer {rest_tok}"}

    delay = app_client.patch(
        f"/abuu/restaurant/orders/{order_id}/prep-delay",
        headers=rest_headers,
        json={"note": "Kitchen delay 15 min"},
    )
    assert delay.status_code == 200
    assert delay.json()["prep_delay_note"] == "Kitchen delay 15 min"

    cancelled = app_client.post(
        f"/admin/abuu/orders/{order_id}/cancel-paid",
        headers=headers,
        json={"reason": "Customer request"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["refund_ready"] is True

    refunded = app_client.post(f"/admin/abuu/orders/{order_id}/refund-processed", headers=headers)
    assert refunded.status_code == 200
    assert refunded.json()["refund_ready"] is False
