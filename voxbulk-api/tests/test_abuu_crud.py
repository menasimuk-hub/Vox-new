from __future__ import annotations

import uuid

from app.core.abuu_database import run_abuu_migrations
from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User


def _mk_superadmin(app_client):
    with get_sessionmaker()() as db:
        org = Organisation(name="Abuu CRUD Org")
        db.add(org)
        db.flush()
        admin = User(
            email=f"abuu_crud_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
            is_superuser=True,
        )
        db.add(admin)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=admin.id))
        db.commit()
        org_id = org.id
        email = admin.email

    tok = app_client.post(
        "/auth/token",
        data={"username": email, "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_abuu_list_seeded_restaurants(app_client):
    run_abuu_migrations()
    headers = _mk_superadmin(app_client)
    resp = app_client.get("/admin/abuu/restaurants", headers=headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 4
    names = {r["name_en"] for r in rows}
    assert "Al-Akhdar Vegetarian" in names
    assert "Al-Bahr Seafood" in names


def test_abuu_create_driver_and_restaurant_login(app_client):
    run_abuu_migrations()
    headers = _mk_superadmin(app_client)
    driver = app_client.post(
        "/admin/abuu/drivers",
        headers=headers,
        json={
            "name": "Test Driver",
            "login_email": "driver@test.abuu",
            "password": "pass123",
            "is_available": True,
        },
    )
    assert driver.status_code == 200
    tok = app_client.post(
        "/abuu/auth/driver/token",
        data={"username": "driver@test.abuu", "password": "pass123"},
    )
    assert tok.status_code == 200
    assert tok.json()["access_token"]


def test_abuu_mark_paid_flow(app_client):
    run_abuu_migrations()
    headers = _mk_superadmin(app_client)
    from app.core.abuu_database import get_abuu_sessionmaker
    from app.abuu.models.entities import CustomerOrder, CustomerProfile, Restaurant

    with get_abuu_sessionmaker()() as db:
        restaurant = db.execute(
            __import__("sqlalchemy").select(Restaurant).limit(1)
        ).scalar_one()
        customer = CustomerProfile(phone="+972509999999", preferred_language="ar")
        db.add(customer)
        db.flush()
        order = CustomerOrder(
            customer_id=customer.id,
            restaurant_id=restaurant.id,
            status="confirmed",
            payment_status="pending_manual",
            total_agorot=4500,
            currency="ILS",
        )
        db.add(order)
        db.commit()
        order_id = order.id

    paid = app_client.post(f"/admin/abuu/orders/{order_id}/mark-paid", headers=headers)
    assert paid.status_code == 200
    body = paid.json()
    assert body["status"] == "sent_to_restaurant"
    assert body["payment_status"] == "paid_manual"


def test_abuu_mark_paid_with_multiple_drivers(app_client):
    run_abuu_migrations()
    headers = _mk_superadmin(app_client)
    from app.core.abuu_database import get_abuu_sessionmaker
    from app.abuu.models.entities import CustomerOrder, CustomerProfile, Restaurant

    for idx in range(2):
        app_client.post(
            "/admin/abuu/drivers",
            headers=headers,
            json={
                "name": f"Driver {idx}",
                "login_email": f"multi_driver_{idx}@test.abuu",
                "password": "pass123",
                "is_available": True,
            },
        )

    with get_abuu_sessionmaker()() as db:
        restaurant = db.execute(
            __import__("sqlalchemy").select(Restaurant).limit(1)
        ).scalar_one()
        customer = CustomerProfile(phone="+972509999998", preferred_language="ar")
        db.add(customer)
        db.flush()
        order = CustomerOrder(
            customer_id=customer.id,
            restaurant_id=restaurant.id,
            status="confirmed",
            payment_status="pending_manual",
            total_agorot=4500,
            currency="ILS",
        )
        db.add(order)
        db.commit()
        order_id = order.id

    paid = app_client.post(f"/admin/abuu/orders/{order_id}/mark-paid", headers=headers)
    assert paid.status_code == 200
    assert paid.json()["status"] == "sent_to_restaurant"
