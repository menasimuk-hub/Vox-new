from __future__ import annotations

import uuid
from unittest.mock import patch

from app.core.abuu_database import get_abuu_sessionmaker, run_abuu_migrations
from app.abuu.models.entities import AbuuNotification, CustomerOrder, CustomerProfile, Driver, Restaurant
from tests.test_abuu_crud import _mk_superadmin


def test_abuu_notifications_on_paid(app_client):
    run_abuu_migrations()
    headers = _mk_superadmin(app_client)

    with get_abuu_sessionmaker()() as db:
        restaurant = db.execute(
            __import__("sqlalchemy").select(Restaurant).limit(1)
        ).scalar_one()
        customer = CustomerProfile(phone=f"+97250{uuid.uuid4().int % 10_000_000:07d}", preferred_language="ar")
        db.add(customer)
        db.flush()
        order = CustomerOrder(
            customer_id=customer.id,
            restaurant_id=restaurant.id,
            status="confirmed",
            payment_status="pending_manual",
            total_agorot=3000,
        )
        db.add(order)
        db.commit()
        order_id = order.id
        restaurant_id = restaurant.id

    resp = app_client.post(f"/admin/abuu/orders/{order_id}/mark-paid", headers=headers)
    assert resp.status_code == 200

    with get_abuu_sessionmaker()() as db:
        rows = db.execute(
            __import__("sqlalchemy").select(AbuuNotification).where(
                AbuuNotification.order_id == order_id,
                AbuuNotification.target_type == "restaurant",
                AbuuNotification.target_id == restaurant_id,
            )
        ).scalars().all()
    assert len(rows) >= 1
    assert rows[0].kind == "order_paid"


def test_abuu_notification_on_delivered(app_client):
    run_abuu_migrations()
    headers = _mk_superadmin(app_client)
    from app.core.security import hash_password

    with get_abuu_sessionmaker()() as db:
        restaurant = db.execute(
            __import__("sqlalchemy").select(Restaurant).limit(1)
        ).scalar_one()
        customer = CustomerProfile(phone=f"+97251{uuid.uuid4().int % 10_000_000:07d}", preferred_language="ar")
        db.add(customer)
        db.flush()
        order = CustomerOrder(
            customer_id=customer.id,
            restaurant_id=restaurant.id,
            status="picked_up",
            payment_status="paid_manual",
            total_agorot=3000,
        )
        db.add(order)
        db.flush()
        driver = Driver(
            name="Notify Driver",
            login_email=f"notify_{uuid.uuid4().hex[:6]}@abuu.test",
            password_hash=hash_password("pass123"),
            is_available=True,
            status="active",
        )
        db.add(driver)
        db.flush()
        for seed_driver in db.execute(
            __import__("sqlalchemy").select(Driver).where(Driver.id != driver.id)
        ).scalars().all():
            seed_driver.is_available = False
            db.add(seed_driver)
        from app.abuu.models.entities import DeliveryAssignment

        assignment = DeliveryAssignment(
            order_id=order.id,
            driver_id=driver.id,
            status="on_route",
        )
        db.add(assignment)
        db.commit()
        assignment_id = assignment.id
        order_id = order.id
        driver_email = driver.login_email

    driver_tok = app_client.post(
        "/abuu/auth/driver/token",
        data={"username": driver_email, "password": "pass123"},
    )
    assert driver_tok.status_code == 200, driver_tok.text
    app_client.patch(
        f"/abuu/driver/assignments/{assignment_id}",
        headers={"Authorization": f"Bearer {driver_tok.json()['access_token']}"},
        json={"status": "delivered"},
    )

    with get_abuu_sessionmaker()() as db:
        rows = db.execute(
            __import__("sqlalchemy").select(AbuuNotification).where(
                AbuuNotification.order_id == order_id,
                AbuuNotification.kind == "order_delivered",
            )
        ).scalars().all()
    assert len(rows) >= 1
