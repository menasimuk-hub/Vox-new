from __future__ import annotations

from unittest.mock import patch

from app.abuu.services.inbound_service import AbuuInboundService
from app.abuu.services.intent_service import detect_intent, is_abuu_start_message
from app.abuu.services.preference_service import match_food_categories


def test_abuu_intent_detection():
    assert detect_intent("طلب", has_active_session=False).name == "order_food"
    assert detect_intent("abuu", has_active_session=False).name == "order_food"
    assert detect_intent("تأكيد", has_active_session=True).name == "confirm"
    assert detect_intent("3", has_active_session=True).name == "add_item"
    assert detect_intent("Ahmad", has_active_session=True, step="awaiting_name").name == "provide_name"
    assert is_abuu_start_message("order food") is True


def test_preference_category_matching():
    assert "chicken" in match_food_categories("I want chicken")
    assert "fish" in match_food_categories("سمك")
    assert "salad" in match_food_categories("سلطة")
    assert len(match_food_categories("chicken and fish")) >= 2


@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
def test_abuu_whatsapp_order_flow(mock_send, app_client):
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    with get_sessionmaker()() as db:
        org = Organisation(name="Abuu WA Org")
        db.add(org)
        db.commit()
        org_id = org.id

    phone = "+972501234567"
    with get_sessionmaker()() as db:
        result = AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="abuu",
            message_id="msg-abuu-1",
            org_id=org_id,
        )
    assert result.get("handled") is True
    assert result.get("action") == "started"
    assert result.get("step") == "awaiting_name"

    with get_sessionmaker()() as db:
        name_result = AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="Ahmad",
            message_id="msg-abuu-1b",
            org_id=org_id,
        )
    assert name_result.get("action") == "name_saved"

    with get_sessionmaker()() as db:
        pref_result = AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="chicken",
            message_id="msg-abuu-1c",
            org_id=org_id,
        )
    assert pref_result.get("action") == "preference_menu"

    with get_sessionmaker()() as db:
        add_result = AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="1",
            message_id="msg-abuu-2",
            org_id=org_id,
        )
    assert add_result.get("handled") is True
    assert add_result.get("action") == "item_added"

    with get_sessionmaker()() as db:
        confirm_result = AbuuInboundService.try_handle(
            db,
            from_phone=phone,
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
            "location": {"latitude": 31.354, "longitude": 34.308, "address": "Gaza City"},
        },
    }
    with get_sessionmaker()() as db:
        loc_result = AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="",
            message_id="msg-abuu-4",
            record=location_record,
            org_id=org_id,
        )
    assert loc_result.get("handled") is True
    assert loc_result.get("action") == "confirmed"

    with get_sessionmaker()() as db:
        from app.core.abuu_database import get_abuu_sessionmaker
        from app.abuu.models.entities import CustomerAddress, CustomerOrder, CustomerProfile

        with get_abuu_sessionmaker()() as abuu_db:
            customer = abuu_db.execute(
                __import__("sqlalchemy").select(CustomerProfile).where(CustomerProfile.phone == phone)
            ).scalar_one()
            assert customer.name == "Ahmad"
            order = abuu_db.execute(
                __import__("sqlalchemy").select(CustomerOrder).order_by(CustomerOrder.created_at.desc())
            ).scalars().first()
            assert order.status == "confirmed"
            addr = abuu_db.get(CustomerAddress, order.delivery_address_id)
            assert addr.source_message_id == "msg-abuu-4"

    assert mock_send.call_count >= 6


@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
@patch("app.abuu.services.inbound_service.AbuuVoiceService.transcribe_inbound")
def test_abuu_voice_note_transcription_flow(mock_transcribe, mock_send, app_client):
    from app.abuu.services.abuu_voice_service import AbuuVoiceTranscription
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    mock_transcribe.return_value = AbuuVoiceTranscription(
        ok=True,
        transcript="chicken",
        confidence=0.92,
        media_url="https://example.com/voice.ogg",
        content_type="audio/ogg",
        storage_path="/tmp/voice.ogg",
    )

    with get_sessionmaker()() as db:
        org = Organisation(name="Abuu Voice Org")
        db.add(org)
        db.commit()
        org_id = org.id

    phone = "+972501234568"
    with get_sessionmaker()() as db:
        AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="abuu",
            message_id="msg-voice-1",
            org_id=org_id,
        )
        AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="Sara",
            message_id="msg-voice-1b",
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
            from_phone=phone,
            body="media-id-12345",
            message_id="msg-voice-2",
            record=voice_record,
            org_id=org_id,
        )
    assert result.get("handled") is True
    assert result.get("action") == "preference_menu"
    mock_transcribe.assert_called_once()


@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
@patch("app.abuu.services.inbound_service.AbuuVoiceService.transcribe_inbound")
def test_abuu_voice_note_low_confidence(mock_transcribe, mock_send, app_client):
    from app.abuu.services.abuu_voice_service import AbuuVoiceTranscription
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    mock_transcribe.return_value = AbuuVoiceTranscription(
        ok=False,
        transcript="",
        confidence=0.1,
        media_url="https://example.com/voice.ogg",
        error="low_confidence_or_empty",
    )

    with get_sessionmaker()() as db:
        org = Organisation(name="Abuu Voice Low Org")
        db.add(org)
        db.commit()
        org_id = org.id

    phone = "+972501234569"
    with get_sessionmaker()() as db:
        AbuuInboundService.try_handle(db, from_phone=phone, body="abuu", message_id="msg-vl-1", org_id=org_id)
        AbuuInboundService.try_handle(db, from_phone=phone, body="Ali", message_id="msg-vl-1b", org_id=org_id)

    voice_record = {
        "type": "audio",
        "media": [{"url": "https://example.com/voice.ogg", "content_type": "audio/ogg"}],
    }
    with get_sessionmaker()() as db:
        result = AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="",
            message_id="msg-vl-2",
            record=voice_record,
            org_id=org_id,
        )
    assert result.get("reason") == "voice_low_confidence"
    reply = mock_send.call_args.kwargs.get("body") or mock_send.call_args.args[2]
    assert "كتابة" in reply or "type" in reply.lower()


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
            from_phone="+972501234570",
            body='Hi! feedback for Acme at Branch. acme-branch-a3f2b1',
            message_id="msg-fb-1",
        )
    assert result.get("handled") is False
    mock_send.assert_not_called()
