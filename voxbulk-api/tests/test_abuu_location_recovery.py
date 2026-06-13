from __future__ import annotations

import uuid
from unittest.mock import patch

from app.abuu.models.entities import CustomerOrder, CustomerOrderItem, CustomerProfile, Restaurant, RestaurantMenuItem
from app.core.abuu_database import get_abuu_sessionmaker, run_abuu_migrations
from tests.test_abuu_crud import _mk_superadmin


def test_normalize_address_strips_prefix():
    from app.abuu.services.location_service import normalize_address_text

    assert normalize_address_text("Address: Gaza City center") == "Gaza City center"


@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
@patch("app.abuu.services.inbound_service.forward_geocode")
def test_typed_gaza_address_geocoded(mock_geocode, mock_send):
    from app.abuu.services.location_service import GeocodeResult

    run_abuu_migrations()
    mock_geocode.return_value = GeocodeResult(
        latitude=31.354,
        longitude=34.308,
        display_name="Gaza City, Gaza Strip",
    )

    from app.abuu.services.inbound_service import AbuuInboundService
    from app.core.database import get_sessionmaker

    phone = f"+97259{uuid.uuid4().int % 10_000_000:07d}"
    with get_abuu_sessionmaker()() as abuu_db:
        restaurant = abuu_db.execute(__import__("sqlalchemy").select(Restaurant).limit(1)).scalar_one()
        customer = CustomerProfile(phone=phone, preferred_language="ar")
        abuu_db.add(customer)
        abuu_db.flush()
        order = CustomerOrder(
            customer_id=customer.id,
            restaurant_id=restaurant.id,
            status="draft",
            total_agorot=4500,
            location_missing=True,
        )
        abuu_db.add(order)
        abuu_db.flush()
        from app.abuu.services.order_draft_service import AbuuOrderDraftService

        AbuuOrderDraftService.upsert_session(
            abuu_db,
            phone=phone,
            step="awaiting_delivery",
            context={"restaurant_id": restaurant.id},
            active_order_id=order.id,
        )
        abuu_db.commit()
        order_id = order.id

    with get_sessionmaker()() as main_db:
        result = AbuuInboundService.try_handle(
            main_db,
            from_phone=phone,
            body="Gaza City center",
            message_id=f"msg-{uuid.uuid4().hex}",
        )

    assert result.get("handled") is True
    assert result.get("action") == "address_saved"

    with get_abuu_sessionmaker()() as db:
        order = db.get(CustomerOrder, order_id)
        assert order.location_missing is False
        assert order.delivery_address_id is not None


@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
def test_location_missing_flag_on_confirm_without_address(mock_send, app_client):
    run_abuu_migrations()
    headers = _mk_superadmin(app_client)

    with get_abuu_sessionmaker()() as db:
        restaurant = db.execute(__import__("sqlalchemy").select(Restaurant).limit(1)).scalar_one()
        customer = CustomerProfile(phone=f"+97258{uuid.uuid4().int % 10_000_000:07d}", preferred_language="ar")
        db.add(customer)
        db.flush()
        order = CustomerOrder(
            customer_id=customer.id,
            restaurant_id=restaurant.id,
            status="draft",
            total_agorot=4500,
        )
        db.add(order)
        db.flush()
        item = db.execute(__import__("sqlalchemy").select(RestaurantMenuItem).limit(1)).scalar_one()
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
        from app.abuu.services.order_draft_service import AbuuOrderDraftService

        AbuuOrderDraftService.upsert_session(
            db,
            phone=customer.phone,
            step="browsing",
            context={"restaurant_id": restaurant.id, "suggested_items": []},
            active_order_id=order.id,
        )
        db.commit()
        order_id = order.id
        customer_phone = customer.phone

    from app.abuu.services.inbound_service import AbuuInboundService
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as main_db:
        result = AbuuInboundService.try_handle(
            main_db,
            from_phone=customer_phone,
            body="confirm",
            message_id=f"confirm-{uuid.uuid4().hex}",
        )

    assert result.get("action") == "need_delivery_address"
    detail = app_client.get(f"/admin/abuu/orders/{order_id}", headers=headers).json()
    assert detail["location_missing"] is True
