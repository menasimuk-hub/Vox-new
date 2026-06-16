"""WhatsApp number routing: Abuu only on Yallasay line (+447822002099), not survey line (+447822002055)."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.services.telnyx_inbound_messaging_service import TelnyxInboundMessagingService

YALLASAY_WA = "+447822002099"  # Number 2 — Abuu / YallaSay only
SURVEY_WA = "+447822002055"  # Number 1 — surveys only
CUSTOMER = "+447700900123"
YALLASAY_PROFILE = "40019e47-a9de-45bb-8e93-9e1abb3521cc"
SURVEY_PROFILE = "50019e47-a9de-45bb-8e93-9e1abb3521cc"


@pytest.fixture
def telnyx_numbers():
    config = {
        "api_key": "KEY_test_telnyx",
        "sms_from_2": YALLASAY_WA,
        "whatsapp_from_2": YALLASAY_WA,
        "whatsapp_from": SURVEY_WA,
        "whatsapp_messaging_profile_id_2": YALLASAY_PROFILE,
        "whatsapp_messaging_profile_id": SURVEY_PROFILE,
    }
    with patch(
        "app.services.yallasay_telnyx_line.ProviderSettingsService.get_platform_config_decrypted",
        return_value=(config, True),
    ):
        yield config


def _wa_payload(
    *,
    to_number: str | None = None,
    message_id: str,
    text: str = "Yallasay",
    messaging_profile_id: str | None = None,
) -> dict:
    payload: dict = {
        "id": message_id,
        "direction": "inbound",
        "type": "WHATSAPP",
        "from": {"phone_number": CUSTOMER},
        "body": {"type": "text", "text": {"body": text}},
        "status": "received",
    }
    if to_number:
        payload["to"] = [{"phone_number": to_number}]
    if messaging_profile_id:
        payload["messaging_profile_id"] = messaging_profile_id
    return {
        "data": {
            "event_type": "message.received",
            "payload": payload,
        }
    }


@patch("app.abuu.services.inbound_service.AbuuInboundService.try_handle")
def test_survey_wa_number_does_not_call_abuu(mock_abuu, app_client, telnyx_numbers):
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    mock_abuu.return_value = {"handled": True}

    with get_sessionmaker()() as db:
        org = Organisation(name="Survey WA Routing Org")
        db.add(org)
        db.commit()
        org_id = org.id

    msg_id = f"wa-survey-{uuid.uuid4().hex[:10]}"
    r = app_client.post(
        "/telnyx/webhooks/messages",
        json=_wa_payload(to_number=SURVEY_WA, message_id=msg_id),
        headers={"X-Retover-Org-Id": org_id},
    )
    assert r.status_code == 200
    mock_abuu.assert_not_called()


@patch("app.abuu.services.inbound_service.AbuuInboundService.try_handle")
def test_yallasay_wa_number_routes_to_abuu_with_reply_from(mock_abuu, app_client, telnyx_numbers):
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    mock_abuu.return_value = {"handled": True, "action": "agent_reply"}

    with get_sessionmaker()() as db:
        org = Organisation(name="Yallasay WA Routing Org")
        db.add(org)
        db.commit()
        org_id = org.id

    msg_id = f"wa-yalla-{uuid.uuid4().hex[:10]}"
    r = app_client.post(
        "/telnyx/webhooks/messages",
        json=_wa_payload(to_number=YALLASAY_WA, message_id=msg_id),
        headers={"X-Retover-Org-Id": org_id},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("yallasay_line") is True
    mock_abuu.assert_called_once()
    assert mock_abuu.call_args.kwargs.get("reply_from") == YALLASAY_WA
    assert mock_abuu.call_args.kwargs.get("reply_channel") == "whatsapp"


@patch("app.abuu.services.inbound_service.AbuuInboundService.try_handle")
def test_yallasay_wa_inferred_from_profile_when_to_missing(mock_abuu, app_client, telnyx_numbers):
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation
    from app.models.whatsapp_log import WhatsAppLog

    mock_abuu.return_value = {"handled": True, "action": "agent_reply"}

    with get_sessionmaker()() as db:
        org = Organisation(name="Yallasay WA inferred to org")
        db.add(org)
        db.commit()
        org_id = org.id

    msg_id = f"wa-yalla-noto-{uuid.uuid4().hex[:10]}"
    r = app_client.post(
        "/telnyx/webhooks/messages",
        json=_wa_payload(
            message_id=msg_id,
            messaging_profile_id=YALLASAY_PROFILE,
        ),
        headers={"X-Retover-Org-Id": org_id},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("yallasay_line") is True
    mock_abuu.assert_called_once()

    with get_sessionmaker()() as db:
        from sqlalchemy import select

        row = db.execute(
            select(WhatsAppLog).where(WhatsAppLog.external_message_id == msg_id)
        ).scalar_one()
        assert row.to_number == YALLASAY_WA


@patch("app.abuu.services.inbound_service.AbuuInboundService.try_handle")
def test_survey_profile_without_to_does_not_call_abuu(mock_abuu, app_client, telnyx_numbers):
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    mock_abuu.return_value = {"handled": True}

    with get_sessionmaker()() as db:
        org = Organisation(name="Survey WA inferred to org")
        db.add(org)
        db.commit()
        org_id = org.id

    msg_id = f"wa-survey-noto-{uuid.uuid4().hex[:10]}"
    r = app_client.post(
        "/telnyx/webhooks/messages",
        json=_wa_payload(
            message_id=msg_id,
            messaging_profile_id=SURVEY_PROFILE,
            text="Start survey",
        ),
        headers={"X-Retover-Org-Id": org_id},
    )
    assert r.status_code == 200
    mock_abuu.assert_not_called()


@patch("app.abuu.services.inbound_service.AbuuInboundService.try_handle")
def test_missing_to_and_profile_does_not_call_abuu(mock_abuu, app_client, telnyx_numbers):
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    with get_sessionmaker()() as db:
        org = Organisation(name="WA no to no profile org")
        db.add(org)
        db.commit()
        org_id = org.id

    msg_id = f"wa-noto-{uuid.uuid4().hex[:10]}"
    r = app_client.post(
        "/telnyx/webhooks/messages",
        json=_wa_payload(message_id=msg_id),
        headers={"X-Retover-Org-Id": org_id},
    )
    assert r.status_code == 200
    mock_abuu.assert_not_called()


def test_telnyx_source_has_no_shared_path_abuu():
    from app.services import telnyx_inbound_messaging_service as mod

    source = open(mod.__file__, encoding="utf-8").read()
    assert "handled_abuu" not in source
    assert "abuu_wa_inbound_handler_failed" not in source
