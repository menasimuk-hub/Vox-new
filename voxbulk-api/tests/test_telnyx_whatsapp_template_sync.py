from __future__ import annotations

from datetime import datetime

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.telnyx_whatsapp_template_sync_service import (
    TelnyxWhatsappTemplateSyncService,
    send_template_id_for_row,
)


def test_sync_upserts_templates(app_client, monkeypatch):
    remote = [
        {
            "id": "019cd44b-offer-telnyx-uuid",
            "template_id": "1909771389734817",
            "name": "voxbulk_sales_offer",
            "language": "en_US",
            "category": "MARKETING",
            "status": "APPROVED",
            "components": [
                {
                    "type": "BODY",
                    "text": "Hi {{1}}, your {{2}} is ready: {{3}}",
                },
                {
                    "type": "BUTTONS",
                    "buttons": [{"type": "URL", "text": "Start account", "url": "https://voxbulk.com/signin?{{1}}"}],
                },
            ],
        },
        {
            "id": "019cd44b-optin-telnyx-uuid",
            "template_id": "1909771389734818",
            "name": "voxbulk_sales_opt_in",
            "language": "en_US",
            "status": "APPROVED",
            "components": [{"type": "BODY", "text": "Hi {{1}}"}],
        },
    ]

    monkeypatch.setattr(
        "app.services.telnyx_whatsapp_template_sync_service.TelnyxWhatsappTemplateSyncService.fetch_from_telnyx",
        lambda db: remote,
    )

    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        result = TelnyxWhatsappTemplateSyncService.sync(db)
        assert result["synced"] == 2
        assert result["approved"] == 2

        offer = TelnyxWhatsappTemplateSyncService.get_for_sales_key(db, "sales_offer")
        assert offer is not None
        assert offer.template_id == "019cd44b-offer-telnyx-uuid"
        assert offer.sales_template_key == "sales_offer"
        assert offer.language == "en_US"

        components = TelnyxWhatsappTemplateSyncService.build_components_for_row(offer)
        assert components is not None
        assert components[0]["type"] == "body"
        assert len(components[0]["parameters"]) == 3
        assert components[1]["type"] == "button"
        assert send_template_id_for_row(offer) == "019cd44b-offer-telnyx-uuid"


def test_build_components_url_button_without_stored_components(app_client):
    from app.core.database import get_sessionmaker
    from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService

    with get_sessionmaker()() as db:
        now = datetime.utcnow()
        row = TelnyxWhatsappTemplate(
            telnyx_record_id="rec-offer",
            template_id="rec-offer",
            name="voxbulk_sales_offer",
            language="en_US",
            status="APPROVED",
            sales_template_key="sales_offer",
            components_json=None,
            synced_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        components = TelnyxWhatsappTemplateSyncService.build_components_for_row(
            row,
            variables={"first_name": "Tom", "offer_line": "trial", "offer_summary": "Offer", "signup_url": "https://voxbulk.com/signin?promo=TEST"},
        )
        assert components is not None
        assert any(c.get("type") == "button" for c in components)


def test_resolve_for_send_by_template_id(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        now = datetime.utcnow()
        db.add(
            TelnyxWhatsappTemplate(
                telnyx_record_id="rec-1",
                template_id="tpl-uuid-123",
                name="voxbulk_sales_followup",
                language="en_US",
                status="APPROVED",
                sales_template_key="sales_offer_followup",
                synced_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()

        row = TelnyxWhatsappTemplateSyncService.resolve_for_send(db, template_id="tpl-uuid-123")
        assert row is not None
        assert row.name == "voxbulk_sales_followup"
