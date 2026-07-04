"""Meta WhatsApp webhook — delivery status + inbound routing."""

from __future__ import annotations

import json

import pytest

from app.core.database import get_sessionmaker
from app.models.whatsapp_log import WhatsAppLog
from app.services.messaging_log_service import LogService
from app.services.meta_whatsapp_inbound_service import MetaWhatsappInboundService


@pytest.fixture(autouse=True)
def _schema():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def test_meta_webhook_updates_delivery_status():
    wamid = "wamid.test.delivery.status"
    with get_sessionmaker()() as db:
        LogService.create_whatsapp_log(
            db,
            org_id="org-1",
            direction="outbound",
            from_number="+447822002055",
            to_number="+447954823445",
            body="Welcome",
            status="sent",
            external_message_id=wamid,
            provider="meta_whatsapp",
        )
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "waba-1",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "statuses": [
                                    {
                                        "id": wamid,
                                        "status": "delivered",
                                        "timestamp": "1710000000",
                                        "recipient_id": "447954823445",
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
        result = MetaWhatsappInboundService.handle_webhook(db, payload=payload)
        assert result["status_updated"] == 1
        row = db.get(WhatsAppLog, 1)
        assert row is not None
        assert row.status == "delivered"


def test_meta_webhook_marks_failed_delivery():
    wamid = "wamid.test.failed"
    with get_sessionmaker()() as db:
        LogService.create_whatsapp_log(
            db,
            org_id="org-1",
            direction="outbound",
            from_number="+447822002055",
            to_number="+447954823445",
            body="Welcome",
            status="sent",
            external_message_id=wamid,
            provider="meta_whatsapp",
        )
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "statuses": [
                                    {
                                        "id": wamid,
                                        "status": "failed",
                                        "errors": [{"title": "Message undeliverable"}],
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        MetaWhatsappInboundService.handle_webhook(db, payload=payload)
        row = db.get(WhatsAppLog, 1)
        assert row.status == "delivery_failed"
        assert "Message undeliverable" in (row.body or "")
