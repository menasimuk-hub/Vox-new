from __future__ import annotations

from app.services.telnyx_messaging_service import TelnyxMessagingService


def test_message_detail_from_data_merges_to_errors_and_meta():
    data = {
        "id": "40319e51-1ee0-4d5f-b51c-179d38beb363",
        "direction": "outbound",
        "type": "whatsapp",
        "from": {"phone_number": "+15551234567"},
        "to": [
            {
                "phone_number": "+447700900123",
                "status": "delivery_failed",
                "errors": [
                    {
                        "code": "40008",
                        "title": "Undeliverable",
                        "detail": "The recipient carrier did not accept the message.",
                        "meta": {
                            "whatsapp_error_code": "131026",
                            "error_user_msg": "Message undeliverable",
                        },
                    }
                ],
            }
        ],
    }
    detail = TelnyxMessagingService.message_detail_from_data(data)
    assert detail["status"] == "delivery_failed"
    assert len(detail["errors"]) == 1
    assert detail["errors"][0]["meta"]["whatsapp_error_code"] == "131026"
    assert "131026" in (detail["error_summary"] or "")
    assert "40008" in (detail["error_summary"] or "")


def test_log_outbound_accepts_uk_local_to_number():
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation
    from app.services.telnyx_messaging_service import TelnyxMessageResult, TelnyxMessagingService

    with get_sessionmaker()() as db:
        org = Organisation(name="WA Log UK Org")
        db.add(org)
        db.commit()
        result = TelnyxMessageResult(ok=True, status="queued", external_id="msg-uk-07-test")
        row = TelnyxMessagingService.log_outbound(
            db,
            org_id=org.id,
            to_number="07954823445",
            from_number="+447822002055",
            body="test",
            result=result,
        )
        assert row.id
        assert row.to_number == "+447954823445"
