from __future__ import annotations

import uuid
from datetime import datetime

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.models.survey_type_template import SurveyTypeTemplate
from app.services.survey_type_service import SurveyTypeService
from app.services.survey_type_template_service import SurveyTypeTemplateService
from app.services.telnyx_whatsapp_template_sync_service import (
    TelnyxWhatsappTemplateSyncService,
    send_template_id_for_row,
)


def test_sync_maps_legacy_interview_confirm_name_to_canonical(app_client, monkeypatch):
    remote = [
        {
            "id": "019confirm-legacy",
            "template_id": "555",
            "name": "voxbulk_interview_confirm",
            "language": "en_GB",
            "category": "UTILITY",
            "status": "APPROVED",
            "components": [{"type": "BODY", "text": "Hi {{1}}", "example": {"body_text": [["James"]]}}],
        },
    ]

    monkeypatch.setattr(
        "app.services.telnyx_whatsapp_template_sync_service.TelnyxWhatsappTemplateSyncService.fetch_from_telnyx",
        lambda db: remote,
    )

    from app.core.database import get_sessionmaker
    from app.services.interview_whatsapp_template_service import InterviewWhatsappTemplateService

    with get_sessionmaker()() as db:
        result = TelnyxWhatsappTemplateSyncService.sync(db)
        assert result["synced"] == 1
        row = TelnyxWhatsappTemplateSyncService.get_for_sales_key(db, "interview_booking_confirm")
        assert row is not None
        assert row.name == "interview_confirm_book"
        assert row.sales_template_key == "interview_booking_confirm"

        listed = InterviewWhatsappTemplateService.list_templates(db)
        confirm = next(item for item in listed if item["sales_template_key"] == "interview_booking_confirm")
        assert confirm["name"] == "interview_confirm_book"


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


def test_sync_removes_stale_local_templates(app_client, monkeypatch):
    remote = [
        {
            "id": "019cd44b-offer-telnyx-uuid",
            "template_id": "1909771389734817",
            "name": "voxbulk_sales_offer",
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
        now = datetime.utcnow()
        db.add(
            TelnyxWhatsappTemplate(
                telnyx_record_id="ghost-deleted-template",
                template_id="ghost-uuid",
                name="old_template_removed_from_telnyx",
                language="en_US",
                status="APPROVED",
                synced_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()

        result = TelnyxWhatsappTemplateSyncService.sync(db)
        assert result["removed"] == 1
        assert result["synced"] == 1
        stored = TelnyxWhatsappTemplateSyncService.list_stored(db)
        assert len(stored) == 1
        assert stored[0]["name"] == "voxbulk_sales_offer"


def test_sync_preserves_local_draft_rows(app_client, monkeypatch):
    remote = [
        {
            "id": "019cd44b-offer-telnyx-uuid",
            "template_id": "1909771389734817",
            "name": "voxbulk_sales_offer",
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
        now = datetime.utcnow()
        SurveyTypeService.ensure_defaults(db)
        survey_type = SurveyTypeService.get_by_slug(db, "customer_satisfaction")
        assert survey_type is not None
        local = TelnyxWhatsappTemplate(
            telnyx_record_id=f"local-{uuid.uuid4().hex}",
            template_id=f"local-{uuid.uuid4().hex}",
            name="voxbulk_survey_food_quality_hospitality_food_food_quality_rating",
            language="en_US",
            status="LOCAL_DRAFT",
            sales_template_key=None,
            synced_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(local)
        db.flush()
        SurveyTypeTemplateService.upsert_mapping(
            db,
            survey_type_id=survey_type.id,
            template_id=local.id,
            usable_as_standard=True,
        )
        db.commit()

        result = TelnyxWhatsappTemplateSyncService.sync(db)
        assert result["synced"] == 1
        assert result["removed"] == 0
        kept = db.get(TelnyxWhatsappTemplate, local.id)
        assert kept is not None
        assert str(kept.telnyx_record_id).startswith("local-")


def test_sync_drops_deleted_remote_status(app_client, monkeypatch):
    remote = [
        {
            "id": "deleted-on-meta",
            "template_id": "999",
            "name": "voxbulk_old",
            "language": "en_US",
            "status": "DELETED",
            "components": [{"type": "BODY", "text": "Hi"}],
        },
    ]

    monkeypatch.setattr(
        "app.services.telnyx_whatsapp_template_sync_service.TelnyxWhatsappTemplateSyncService.fetch_from_telnyx",
        lambda db: remote,
    )

    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        now = datetime.utcnow()
        db.add(
            TelnyxWhatsappTemplate(
                telnyx_record_id="deleted-on-meta",
                template_id="999",
                name="voxbulk_old",
                language="en_US",
                status="APPROVED",
                synced_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()

        result = TelnyxWhatsappTemplateSyncService.sync(db)
        assert result["synced"] == 0
        assert TelnyxWhatsappTemplateSyncService.list_stored(db) == []
