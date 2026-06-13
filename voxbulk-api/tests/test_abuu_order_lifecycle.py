from __future__ import annotations

import uuid

from app.core.abuu_database import get_abuu_sessionmaker, run_abuu_migrations
from app.core.security import hash_password
from app.abuu.models.entities import (
    CustomerAddress,
    CustomerOrder,
    CustomerProfile,
    Driver,
    Restaurant,
)
from tests.test_abuu_crud import _mk_superadmin


def test_abuu_full_order_lifecycle(app_client):
    run_abuu_migrations()
    headers = _mk_superadmin(app_client)

    with get_abuu_sessionmaker()() as db:
        restaurant = db.execute(
            __import__("sqlalchemy").select(Restaurant).limit(1)
        ).scalar_one()
        restaurant.login_email = f"rest_{uuid.uuid4().hex[:6]}@abuu.test"
        restaurant.password_hash = hash_password("pass123")
        customer = CustomerProfile(phone="+972507777777", preferred_language="ar", name="Test Customer")
        db.add(customer)
        db.flush()
        address = CustomerAddress(
            customer_id=customer.id,
            address_text="Test Address 1",
            latitude=32.08,
            longitude=34.78,
            is_default=True,
        )
        db.add(address)
        db.flush()
        order = CustomerOrder(
            customer_id=customer.id,
            restaurant_id=restaurant.id,
            status="confirmed",
            payment_status="pending_manual",
            total_agorot=5500,
            delivery_address_id=address.id,
        )
        db.add(order)
        db.flush()

        for idx in range(2):
            db.add(
                Driver(
                    name=f"Lifecycle Driver {idx}",
                    login_email=f"lifecycle_driver_{idx}_{uuid.uuid4().hex[:4]}@abuu.test",
                    password_hash=hash_password("pass123"),
                    status="active",
                    is_available=True,
                )
            )
        for seed_driver in db.execute(
            __import__("sqlalchemy").select(Driver).where(Driver.password_hash.is_(None))
        ).scalars().all():
            seed_driver.is_available = False
            db.add(seed_driver)
        db.commit()
        order_id = order.id
        rest_email = restaurant.login_email

    paid = app_client.post(f"/admin/abuu/orders/{order_id}/mark-paid", headers=headers)
    assert paid.status_code == 200
    assert paid.json()["status"] == "sent_to_restaurant"

    rest_tok = app_client.post(
        "/abuu/auth/restaurant/token",
        data={"username": rest_email, "password": "pass123"},
    ).json()["access_token"]
    rest_headers = {"Authorization": f"Bearer {rest_tok}"}

    prep = app_client.post(f"/abuu/restaurant/orders/{order_id}/preparing", headers=rest_headers, json={})
    assert prep.status_code == 200
    assert prep.json()["status"] == "preparing"

    ready = app_client.post(f"/abuu/restaurant/orders/{order_id}/ready", headers=rest_headers, json={})
    assert ready.status_code == 200
    assert ready.json()["status"] == "assigned_to_driver"
    assert ready.json()["assignment"] is not None

    assignment_id = ready.json()["assignment"]["id"]
    driver_id = ready.json()["assignment"]["driver_id"]
    assert driver_id

    with get_abuu_sessionmaker()() as db:
        driver = db.get(Driver, driver_id)
        driver_email = driver.login_email

    driver_tok = app_client.post(
        "/abuu/auth/driver/token",
        data={"username": driver_email, "password": "pass123"},
    ).json()["access_token"]
    driver_headers = {"Authorization": f"Bearer {driver_tok}"}

    pickup = app_client.patch(
        f"/abuu/driver/assignments/{assignment_id}",
        headers=driver_headers,
        json={"status": "picked_up"},
    )
    assert pickup.status_code == 200
    assert pickup.json()["status"] == "on_route"
    assert pickup.json()["order"]["status"] == "picked_up"
    assert pickup.json()["pickup"]["restaurant_name_en"]
    assert pickup.json()["dropoff"]["address_text"] == "Test Address 1"

    delivered = app_client.patch(
        f"/abuu/driver/assignments/{assignment_id}",
        headers=driver_headers,
        json={"status": "delivered"},
    )
    assert delivered.status_code == 200
    assert delivered.json()["status"] == "delivered"
    assert delivered.json()["order"]["status"] == "delivered"
