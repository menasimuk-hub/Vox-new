from __future__ import annotations

from unittest.mock import patch

from app.abuu.services.inbound_service import AbuuInboundService
from app.abuu.services.intent_service import detect_intent, is_abuu_start_message


def test_abuu_intent_detection():
    assert detect_intent("طلب", has_active_session=False).name == "order_food"
    assert detect_intent("abuu", has_active_session=False).name == "order_food"
    assert detect_intent("تأكيد", has_active_session=True).name == "confirm"
    assert detect_intent("3", has_active_session=True).name == "add_item"
    assert is_abuu_start_message("order food") is True


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
    assert confirm_result.get("action") == "confirmed"
    assert mock_send.call_count >= 3


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
            from_phone="+972501234568",
            body='Hi! feedback for Acme at Branch. acme-branch-a3f2b1',
            message_id="msg-fb-1",
        )
    assert result.get("handled") is False
    mock_send.assert_not_called()
