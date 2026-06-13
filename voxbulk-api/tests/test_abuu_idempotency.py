from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.abuu.models.entities import AbuuExternalEvent, AbuuNotification, CustomerOrder, CustomerProfile, Driver, Restaurant
from app.core.abuu_database import get_abuu_sessionmaker, run_abuu_migrations
from app.core.security import hash_password
from tests.test_abuu_crud import _mk_superadmin


def _setup_paid_order(db):
    restaurant = db.execute(select(Restaurant).limit(1)).scalar_one()
    customer = CustomerProfile(phone=f"+97252{uuid.uuid4().int % 10_000_000:07d}", preferred_language="ar")
    db.add(customer)
    db.flush()
    order = CustomerOrder(
        customer_id=customer.id,
        restaurant_id=restaurant.id,
        status="confirmed",
        payment_status="pending_manual",
        total_agorot=4000,
    )
    db.add(order)
    db.flush()
    return order, restaurant


def test_mark_paid_idempotent_notifications(app_client):
    run_abuu_migrations()
    headers = _mk_superadmin(app_client)

    with get_abuu_sessionmaker()() as db:
        order, restaurant = _setup_paid_order(db)
        db.commit()
        order_id = order.id
        restaurant_id = restaurant.id

    first = app_client.post(f"/admin/abuu/orders/{order_id}/mark-paid", headers=headers)
    second = app_client.post(f"/admin/abuu/orders/{order_id}/mark-paid", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200

    with get_abuu_sessionmaker()() as db:
        count = db.execute(
            select(func.count())
            .select_from(AbuuNotification)
            .where(
                AbuuNotification.order_id == order_id,
                AbuuNotification.kind == "order_paid",
                AbuuNotification.target_id == restaurant_id,
            )
        ).scalar_one()
        events = db.execute(
            select(AbuuExternalEvent).where(
                AbuuExternalEvent.order_id == order_id,
                AbuuExternalEvent.event_type == "mark_paid",
            )
        ).scalars().all()
    assert int(count or 0) == 1
    assert len(events) >= 1


def test_mark_ready_idempotent_driver_notification(app_client):
    run_abuu_migrations()
    headers = _mk_superadmin(app_client)

    with get_abuu_sessionmaker()() as db:
        order, restaurant = _setup_paid_order(db)
        order.status = "preparing"
        order.payment_status = "paid_manual"
        restaurant.login_email = f"rest_idem_{uuid.uuid4().hex[:6]}@abuu.test"
        restaurant.password_hash = hash_password("pass123")
        for idx in range(2):
            db.add(
                Driver(
                    name=f"Idem Driver {idx}",
                    login_email=f"idem_driver_{idx}_{uuid.uuid4().hex[:4]}@abuu.test",
                    password_hash=hash_password("pass123"),
                    status="active",
                    is_available=True,
                )
            )
        db.commit()
        order_id = order.id
        rest_email = restaurant.login_email

    app_client.post(f"/admin/abuu/orders/{order_id}/mark-paid", headers=headers)
    rest_tok = app_client.post(
        "/abuu/auth/restaurant/token",
        data={"username": rest_email, "password": "pass123"},
    ).json()["access_token"]
    rest_headers = {"Authorization": f"Bearer {rest_tok}"}

    ready1 = app_client.post(f"/abuu/restaurant/orders/{order_id}/ready", headers=rest_headers)
    ready2 = app_client.post(f"/abuu/restaurant/orders/{order_id}/ready", headers=rest_headers)
    assert ready1.status_code == 200
    assert ready2.status_code == 200

    with get_abuu_sessionmaker()() as db:
        count = db.execute(
            select(func.count())
            .select_from(AbuuNotification)
            .where(AbuuNotification.order_id == order_id, AbuuNotification.kind == "order_ready")
        ).scalar_one()
    assert int(count or 0) == 1
