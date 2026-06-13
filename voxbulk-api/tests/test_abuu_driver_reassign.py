from __future__ import annotations

import uuid

from sqlalchemy import select

from app.abuu.models.entities import AbuuAssignmentAttempt, CustomerAddress, CustomerOrder, CustomerProfile, DeliveryAssignment, Driver, Restaurant
from app.core.abuu_database import get_abuu_sessionmaker, run_abuu_migrations
from app.core.security import hash_password
from tests.test_abuu_crud import _mk_superadmin


def test_driver_reject_reassigns_second_driver(app_client):
    run_abuu_migrations()
    headers = _mk_superadmin(app_client)

    with get_abuu_sessionmaker()() as db:
        restaurant = db.execute(select(Restaurant).limit(1)).scalar_one()
        restaurant.login_email = f"rest_rej_{uuid.uuid4().hex[:6]}@abuu.test"
        restaurant.password_hash = hash_password("pass123")
        customer = CustomerProfile(phone=f"+97256{uuid.uuid4().int % 10_000_000:07d}", preferred_language="ar", name="Customer")
        db.add(customer)
        db.flush()
        address = CustomerAddress(
            customer_id=customer.id,
            address_text="Gaza test address",
            latitude=31.354,
            longitude=34.308,
            is_default=True,
        )
        db.add(address)
        db.flush()
        drivers = []
        for idx in range(2):
            d = Driver(
                name=f"Reject Driver {idx}",
                login_email=f"reject_driver_{idx}_{uuid.uuid4().hex[:4]}@abuu.test",
                password_hash=hash_password("pass123"),
                status="active",
                is_available=True,
            )
            db.add(d)
            db.flush()
            drivers.append(d)
        for seed in db.execute(select(Driver).where(Driver.id.notin_([d.id for d in drivers]))).scalars().all():
            seed.is_available = False
            db.add(seed)
        order = CustomerOrder(
            customer_id=customer.id,
            restaurant_id=restaurant.id,
            status="preparing",
            payment_status="paid_manual",
            total_agorot=5000,
            delivery_address_id=address.id,
        )
        db.add(order)
        db.commit()
        order_id = order.id
        rest_email = restaurant.login_email
        driver1_email = drivers[0].login_email
        driver2_id = drivers[1].id

    app_client.post(f"/admin/abuu/orders/{order_id}/mark-paid", headers=headers)
    rest_tok = app_client.post(
        "/abuu/auth/restaurant/token",
        data={"username": rest_email, "password": "pass123"},
    ).json()["access_token"]
    ready = app_client.post(
        f"/abuu/restaurant/orders/{order_id}/ready",
        headers={"Authorization": f"Bearer {rest_tok}"},
    )
    assert ready.status_code == 200
    assignment_id = ready.json()["assignment"]["id"]

    driver1_tok = app_client.post(
        "/abuu/auth/driver/token",
        data={"username": driver1_email, "password": "pass123"},
    ).json()["access_token"]
    rejected = app_client.patch(
        f"/abuu/driver/assignments/{assignment_id}",
        headers={"Authorization": f"Bearer {driver1_tok}"},
        json={"status": "rejected", "reason": "too far"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["driver_id"] == driver2_id
    assert rejected.json()["pickup"]["restaurant_name_en"]
    assert rejected.json()["dropoff"]["customer_name"] == "Customer"
    assert rejected.json()["dropoff"]["address_text"] == "Gaza test address"

    with get_abuu_sessionmaker()() as db:
        attempts = db.execute(
            select(AbuuAssignmentAttempt).where(AbuuAssignmentAttempt.order_id == order_id)
        ).scalars().all()
        statuses = {a.status for a in attempts}
    assert "rejected" in statuses
    assert "assigned" in statuses
