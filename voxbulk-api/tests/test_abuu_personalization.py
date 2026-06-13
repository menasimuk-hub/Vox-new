from __future__ import annotations

import uuid
from unittest.mock import patch

from app.abuu.models.entities import CustomerAddress, CustomerOrder, CustomerProfile, Restaurant
from app.abuu.services.customer_memory_service import first_name, parse_likes
from app.abuu.services.inbound_service import AbuuInboundService
from app.abuu.services.reply_service import personalized_greeting_message
from app.core.abuu_database import get_abuu_sessionmaker, run_abuu_migrations
from app.core.security import hash_password
from tests.test_abuu_crud import _mk_superadmin


def test_personalized_greeting_with_name():
    msg = personalized_greeting_message(first_name="Sara", lang="en")
    assert "Hello Sara" in msg
    assert "chicken" in msg


def test_personalized_greeting_without_name():
    msg = personalized_greeting_message(first_name=None, lang="ar")
    assert "صديقي" in msg


@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
def test_first_message_greeting_with_existing_name(mock_send, app_client):
    run_abuu_migrations()
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    phone = f"+97253{uuid.uuid4().int % 10_000_000:07d}"
    with get_abuu_sessionmaker()() as db:
        db.add(CustomerProfile(phone=phone, name="Mona Hassan", preferred_language="en"))
        db.commit()

    with get_sessionmaker()() as db:
        org = Organisation(name="Greet Org")
        db.add(org)
        db.commit()
        org_id = org.id
        result = AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="abuu",
            message_id=f"msg-{uuid.uuid4().hex[:8]}",
            org_id=org_id,
        )
    assert result.get("step") == "awaiting_preference"
    reply = mock_send.call_args.kwargs.get("body") or mock_send.call_args.args[2]
    assert "Hello Mona" in reply


@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
def test_first_message_asks_name_when_missing(mock_send, app_client):
    run_abuu_migrations()
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    phone = f"+97254{uuid.uuid4().int % 10_000_000:07d}"
    with get_sessionmaker()() as db:
        org = Organisation(name="Name Org")
        db.add(org)
        db.commit()
        org_id = org.id
        result = AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="order food",
            message_id=f"msg-{uuid.uuid4().hex[:8]}",
            org_id=org_id,
        )
    assert result.get("step") == "awaiting_name"
    reply = mock_send.call_args.kwargs.get("body") or mock_send.call_args.args[2]
    assert "name" in reply.lower() or "اسم" in reply


@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
def test_address_reuse_on_start(mock_send, app_client):
    run_abuu_migrations()
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    phone = f"+97255{uuid.uuid4().int % 10_000_000:07d}"
    with get_abuu_sessionmaker()() as db:
        customer = CustomerProfile(phone=phone, name="Yousef", preferred_language="en")
        db.add(customer)
        db.flush()
        db.add(
            CustomerAddress(
                customer_id=customer.id,
                address_text="Gaza saved address",
                latitude=31.354,
                longitude=34.308,
                is_default=True,
            )
        )
        db.commit()

    with get_sessionmaker()() as db:
        org = Organisation(name="Addr Org")
        db.add(org)
        db.commit()
        org_id = org.id
        AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="abuu",
            message_id=f"msg-{uuid.uuid4().hex[:8]}",
            org_id=org_id,
        )
    reply = mock_send.call_args.kwargs.get("body") or mock_send.call_args.args[2]
    assert "Gaza saved address" in reply

    with get_sessionmaker()() as db:
        AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="chicken",
            message_id=f"msg-{uuid.uuid4().hex[:8]}-c",
            org_id=org_id,
        )
        AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="1",
            message_id=f"msg-{uuid.uuid4().hex[:8]}-i",
            org_id=org_id,
        )
        AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="confirm",
            message_id=f"msg-{uuid.uuid4().hex[:8]}-f",
            org_id=org_id,
        )

    with get_abuu_sessionmaker()() as db:
        order = db.execute(__import__("sqlalchemy").select(CustomerOrder).order_by(CustomerOrder.created_at.desc())).scalars().first()
        assert order is not None
        assert order.delivery_address_id is not None


@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
def test_single_confirmation_when_already_confirmed(mock_send, app_client):
    run_abuu_migrations()
    headers = _mk_superadmin(app_client)
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    phone = f"+97256{uuid.uuid4().int % 10_000_000:07d}"
    with get_abuu_sessionmaker()() as db:
        restaurant = db.execute(__import__("sqlalchemy").select(Restaurant).limit(1)).scalar_one()
        customer = CustomerProfile(phone=phone, name="Lina", preferred_language="en")
        db.add(customer)
        db.flush()
        db.add(
            CustomerAddress(
                customer_id=customer.id,
                address_text="Gaza",
                latitude=31.354,
                longitude=34.308,
                is_default=True,
            )
        )
        db.flush()
        order = CustomerOrder(
            customer_id=customer.id,
            restaurant_id=restaurant.id,
            status="confirmed",
            payment_status="pending_manual",
            total_agorot=4500,
            delivery_address_id=db.execute(
                __import__("sqlalchemy").select(CustomerAddress).where(CustomerAddress.customer_id == customer.id)
            ).scalar_one().id,
        )
        db.add(order)
        db.flush()
        from app.abuu.services.order_draft_service import AbuuOrderDraftService

        AbuuOrderDraftService.upsert_session(
            db,
            phone=phone,
            step="browsing",
            context={"restaurant_id": restaurant.id, "suggested_items": []},
            active_order_id=order.id,
        )
        db.commit()
        order_id = order.id

    with get_sessionmaker()() as db:
        org = Organisation(name="Confirm Org")
        db.add(org)
        db.commit()
        org_id = org.id
        result = AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="confirm",
            message_id=f"msg-{uuid.uuid4().hex[:8]}",
            org_id=org_id,
        )
    assert result.get("action") == "already_confirmed"
    detail = app_client.get(f"/admin/abuu/orders/{order_id}", headers=headers).json()
    assert detail["status"] == "confirmed"


@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
def test_preference_remembers_likes(mock_send, app_client):
    run_abuu_migrations()
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    phone = f"+97257{uuid.uuid4().int % 10_000_000:07d}"
    with get_sessionmaker()() as db:
        org = Organisation(name="Pref Org")
        db.add(org)
        db.commit()
        org_id = org.id
        AbuuInboundService.try_handle(db, from_phone=phone, body="abuu", message_id="p1", org_id=org_id)
        AbuuInboundService.try_handle(db, from_phone=phone, body="Omar", message_id="p2", org_id=org_id)
        AbuuInboundService.try_handle(db, from_phone=phone, body="fish", message_id="p3", org_id=org_id)

    with get_abuu_sessionmaker()() as db:
        customer = db.execute(
            __import__("sqlalchemy").select(CustomerProfile).where(CustomerProfile.phone == phone)
        ).scalar_one()
        likes = parse_likes(customer)
    assert "fish" in likes
