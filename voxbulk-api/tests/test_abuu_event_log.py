from __future__ import annotations

import uuid

from app.abuu.models.entities import CustomerOrder, CustomerProfile, Restaurant
from app.core.abuu_database import get_abuu_sessionmaker, run_abuu_migrations
from tests.test_abuu_crud import _mk_superadmin


def test_external_events_list_and_duplicate(app_client):
    run_abuu_migrations()
    headers = _mk_superadmin(app_client)

    with get_abuu_sessionmaker()() as db:
        restaurant = db.execute(__import__("sqlalchemy").select(Restaurant).limit(1)).scalar_one()
        customer = CustomerProfile(phone=f"+97254{uuid.uuid4().int % 10_000_000:07d}", preferred_language="ar")
        db.add(customer)
        db.flush()
        order = CustomerOrder(
            customer_id=customer.id,
            restaurant_id=restaurant.id,
            status="confirmed",
            payment_status="pending_manual",
            total_agorot=3500,
        )
        db.add(order)
        db.commit()
        order_id = order.id

    app_client.post(f"/admin/abuu/orders/{order_id}/mark-paid", headers=headers)
    app_client.post(f"/admin/abuu/orders/{order_id}/mark-paid", headers=headers)

    events = app_client.get(f"/admin/abuu/events?order_id={order_id}", headers=headers)
    assert events.status_code == 200
    rows = events.json()
    assert len(rows) >= 1
    assert any(r["event_type"] == "mark_paid" for r in rows)

    dupes = app_client.get("/admin/abuu/events?status=duplicate", headers=headers)
    assert dupes.status_code == 200
