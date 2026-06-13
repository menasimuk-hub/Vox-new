from __future__ import annotations

from unittest.mock import patch

from app.abuu.services.inbound_service import AbuuInboundService
from app.abuu.services.intent_service import detect_intent, is_abuu_start_message
from app.abuu.services.location_service import (
    parse_whatsapp_location,
)


def test_abuu_intent_detection():
    assert detect_intent("طلب", has_active_session=False).name == "order_food"
    assert detect_intent("abuu", has_active_session=False).name == "order_food"
    assert detect_intent("تأكيد", has_active_session=True).name == "confirm"
    assert detect_intent("3", has_active_session=True).name == "add_item"
    assert is_abuu_start_message("order food") is True


def test_haversine_and_nearest():
    from app.core.abuu_database import get_abuu_sessionmaker
    from app.abuu.models.entities import Restaurant
    from app.abuu.services.location_service import find_nearest_restaurants, haversine_km

    distance = haversine_km(32.0853, 34.7818, 32.0953, 34.7818)
    assert 1.0 < distance < 1.2

    with get_abuu_sessionmaker()() as db:
        db.add(
            Restaurant(
                name_en="Near Test",
                name_ar="Near Test",
                status="active",
                is_available=True,
                latitude=31.9000,
                longitude=35.2000,
                delivery_radius_km=5.0,
            )
        )
        db.add(
            Restaurant(
                name_en="Far Test",
                name_ar="Far Test",
                status="active",
                is_available=True,
                latitude=32.5000,
                longitude=35.8000,
                delivery_radius_km=5.0,
            )
        )
        db.commit()
        ranked = find_nearest_restaurants(db, lat=31.9000, lng=35.2000, limit=2)
    assert ranked[0].restaurant.name_en == "Near Test"
    assert ranked[0].distance_km < ranked[1].distance_km


def test_parse_whatsapp_location():
    record = {
        "type": "location",
        "whatsapp_message": {
            "type": "location",
            "location": {
                "latitude": 32.08,
                "longitude": 34.78,
                "name": "Home",
                "address": "Tel Aviv",
            },
        },
    }
    parsed = parse_whatsapp_location(record)
    assert parsed is not None
    assert parsed.latitude == 32.08
    assert parsed.address_text == "Tel Aviv"


@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
def test_abuu_whatsapp_order_flow(mock_send, app_client):
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    with get_sessionmaker()() as db:
        org = Organisation(name="Abuu WA Org")
        db.add(org)
        db.commit()
        org_id = org.id

    with get_sessionmaker()() as db:
        result = AbuuInboundService.try_handle(
            db,
            from_phone="+972501234567",
            body="abuu",
            message_id="msg-abuu-1",
            org_id=org_id,
        )
    assert result.get("handled") is True
    assert result.get("action") == "started"
    assert mock_send.called

    with get_sessionmaker()() as db:
        add_result = AbuuInboundService.try_handle(
            db,
            from_phone="+972501234567",
            body="1",
            message_id="msg-abuu-2",
            org_id=org_id,
        )
    assert add_result.get("handled") is True
    assert add_result.get("action") == "item_added"

    with get_sessionmaker()() as db:
        confirm_result = AbuuInboundService.try_handle(
            db,
            from_phone="+972501234567",
            body="تأكيد",
            message_id="msg-abuu-3",
            org_id=org_id,
        )
    assert confirm_result.get("handled") is True
    assert confirm_result.get("action") == "need_delivery_address"

    location_record = {
        "type": "location",
        "whatsapp_message": {
            "type": "location",
            "location": {"latitude": 32.08, "longitude": 34.78, "address": "Ramallah"},
        },
    }
    with get_sessionmaker()() as db:
        loc_result = AbuuInboundService.try_handle(
            db,
            from_phone="+972501234567",
            body="",
            message_id="msg-abuu-4",
            record=location_record,
            org_id=org_id,
        )
    assert loc_result.get("handled") is True
    assert loc_result.get("action") == "address_saved"

    with get_sessionmaker()() as db:
        confirm_result = AbuuInboundService.try_handle(
            db,
            from_phone="+972501234567",
            body="تأكيد",
            message_id="msg-abuu-5",
            org_id=org_id,
        )
    assert confirm_result.get("handled") is True
    assert confirm_result.get("action") == "confirmed"
    assert mock_send.call_count >= 5


@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
def test_abuu_voice_note_during_order(mock_send, app_client):
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    with get_sessionmaker()() as db:
        org = Organisation(name="Abuu Voice Org")
        db.add(org)
        db.commit()
        org_id = org.id

    with get_sessionmaker()() as db:
        AbuuInboundService.try_handle(
            db,
            from_phone="+972501234568",
            body="abuu",
            message_id="msg-voice-1",
            org_id=org_id,
        )

    voice_record = {
        "type": "audio",
        "media": [{"url": "https://example.com/voice.ogg", "content_type": "audio/ogg"}],
        "text": "media-id-12345",
    }
    with get_sessionmaker()() as db:
        result = AbuuInboundService.try_handle(
            db,
            from_phone="+972501234568",
            body="media-id-12345",
            message_id="msg-voice-2",
            record=voice_record,
            org_id=org_id,
        )
    assert result.get("handled") is True
    assert result.get("reason") == "voice_fallback"
    reply = mock_send.call_args.kwargs.get("body") or mock_send.call_args.args[2]
    assert "الرسائل الصوتية" in reply or "Voice notes" in reply


@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
def test_abuu_ignores_feedback_trigger(mock_send, app_client):
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    with get_sessionmaker()() as db:
        org = Organisation(name="Abuu Ignore Org")
        db.add(org)
        db.commit()

    with get_sessionmaker()() as db:
        result = AbuuInboundService.try_handle(
            db,
            from_phone="+972501234569",
            body='Hi! feedback for Acme at Branch. acme-branch-a3f2b1',
            message_id="msg-fb-1",
        )
    assert result.get("handled") is False
    mock_send.assert_not_called()
