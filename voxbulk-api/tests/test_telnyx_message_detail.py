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
