"""Tests for HubSpot contact sync v1 (pull, import, write-back)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.hubspot_contact import HubspotContact
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrderRecipient
from app.models.user import User
from app.services.hubspot_connection_service import save_hubspot_config
from app.services.hubspot_contact_sync_service import (
    fetch_and_upsert_contacts,
    import_contacts_to_order,
    is_sync_v1_enabled,
    maybe_sync_survey_result_to_hubspot,
    sync_survey_result_to_hubspot,
)
from app.services.platform_catalog_service import ServiceOrderService
from app.services.provider_settings import ProviderSettingsService


def _enable_hubspot_platform(db, *, contact_sync_v1: bool = True) -> None:
    ProviderSettingsService.upsert_platform_config(
        db,
        provider="hubspot",
        is_enabled=True,
        config={"auth_mode": "private_app", "contact_sync_v1_enabled": contact_sync_v1},
    )


def _seed_org_user(db) -> tuple[Organisation, User]:
    org = Organisation(name="HubSpot Sync Org")
    user = User(email=f"hs-sync-{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("pass123"), is_active=True)
    db.add(org)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
    save_hubspot_config(
        db,
        org.id,
        {"access_token": "tok-sync", "refresh_token": "ref", "hub_id": "42", "account_name": "Test"},
    )
    db.commit()
    return org, user


def _auth_headers(app_client, org: Organisation, user: User) -> dict[str, str]:
    token = app_client.post(
        "/auth/token",
        data={"username": user.email, "password": "pass123", "org_id": org.id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_sync_v1_flag_off_returns_disabled():
    with get_sessionmaker()() as db:
        _enable_hubspot_platform(db, contact_sync_v1=False)
        assert is_sync_v1_enabled(db) is False


def test_sync_v1_flag_on_when_platform_enabled():
    with get_sessionmaker()() as db:
        _enable_hubspot_platform(db, contact_sync_v1=True)
        assert is_sync_v1_enabled(db) is True


def test_sync_endpoint_404_when_flag_off(app_client):
    with get_sessionmaker()() as db:
        org, user = _seed_org_user(db)
        _enable_hubspot_platform(db, contact_sync_v1=False)
        headers = _auth_headers(app_client, org, user)

    res = app_client.post("/service-orders/hubspot/contacts/sync", headers=headers, json={})
    assert res.status_code == 404


def test_fetch_and_upsert_contacts_maps_fields():
    with get_sessionmaker()() as db:
        org, _ = _seed_org_user(db)
        _enable_hubspot_platform(db, contact_sync_v1=True)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "id": "1001",
                    "properties": {
                        "firstname": "Test",
                        "lastname": "User",
                        "email": "test.user@example.com",
                        "phone": "+447700900111",
                    },
                }
            ],
            "paging": {},
        }

        with patch("app.services.hubspot_contact_sync_service.httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.get.return_value = mock_response
            result = fetch_and_upsert_contacts(db, org.id, limit=100)

        assert result["imported"] == 1
        row = db.query(HubspotContact).filter(HubspotContact.org_id == org.id).one()
        assert row.name == "Test User"
        assert row.email == "test.user@example.com"
        assert row.phone == "+447700900111"


def test_import_contacts_to_order_appends_recipients():
    with get_sessionmaker()() as db:
        org, user = _seed_org_user(db)
        _enable_hubspot_platform(db, contact_sync_v1=True)

        contact = HubspotContact(
            id=str(uuid.uuid4()),
            org_id=org.id,
            hubspot_contact_id="1001",
            name="Test User",
            email="test.user@example.com",
            phone="+447700900111",
        )
        db.add(contact)
        db.commit()

        order = ServiceOrderService.create_order(
            db,
            org_id=org.id,
            user_id=user.id,
            service_code="survey",
            title="Draft survey",
            config={"survey_channel": "whatsapp"},
        )
        order.status = "draft"
        db.add(order)
        db.commit()

        result = import_contacts_to_order(
            db,
            org.id,
            order_id=order.id,
            contact_ids=[contact.id],
        )
        assert result["added"] == 1
        recipients = db.query(ServiceOrderRecipient).filter(ServiceOrderRecipient.order_id == order.id).all()
        assert len(recipients) == 1
        assert recipients[0].phone == "+447700900111"


def test_write_back_skipped_when_toggle_off():
    with get_sessionmaker()() as db:
        org, user = _seed_org_user(db)
        _enable_hubspot_platform(db, contact_sync_v1=True)
        save_hubspot_config(db, org.id, {"access_token": "tok", "auto_sync_results_back": False})

        order = ServiceOrderService.create_order(
            db,
            org_id=org.id,
            user_id=user.id,
            service_code="survey",
            title="WA survey",
            config={},
        )
        recipient = ServiceOrderRecipient(
            order_id=order.id,
            row_number=1,
            name="Test User",
            email="test.user@example.com",
            phone="+447700900111",
            status="completed",
            result_json='{"analysis":{"sentiment":"positive","recommend_score":9}}',
        )
        db.add(recipient)
        db.commit()

        with patch("app.services.hubspot_contact_sync_service._create_hubspot_note") as note_mock:
            result = sync_survey_result_to_hubspot(db, org.id, order=order, recipient=recipient)
        assert result.get("skipped") is True
        note_mock.assert_not_called()


def test_write_back_creates_note_when_enabled():
    with get_sessionmaker()() as db:
        org, user = _seed_org_user(db)
        _enable_hubspot_platform(db, contact_sync_v1=True)
        save_hubspot_config(db, org.id, {"access_token": "tok", "auto_sync_results_back": True})

        order = ServiceOrderService.create_order(
            db,
            org_id=org.id,
            user_id=user.id,
            service_code="survey",
            title="WA survey",
            config={},
        )
        recipient = ServiceOrderRecipient(
            order_id=order.id,
            row_number=1,
            name="Test User",
            email="test.user@example.com",
            phone="+447700900111",
            status="completed",
            result_json='{"analysis":{"sentiment":"positive","recommend_score":9,"short_summary":"Great experience"}}',
        )
        db.add(recipient)
        db.commit()

        with patch(
            "app.services.hubspot_contact_sync_service._search_contact_by_email",
            return_value="hs-1001",
        ), patch("app.services.hubspot_contact_sync_service._update_hubspot_contact_properties") as props_mock, patch(
            "app.services.hubspot_contact_sync_service._create_hubspot_note"
        ) as note_mock:
            result = sync_survey_result_to_hubspot(db, org.id, order=order, recipient=recipient)

        assert result["ok"] is True
        assert result["contact_id"] == "hs-1001"
        props_mock.assert_called_once()
        note_mock.assert_called_once()


def test_manual_push_bypasses_auto_sync_toggle():
    with get_sessionmaker()() as db:
        org, user = _seed_org_user(db)
        _enable_hubspot_platform(db, contact_sync_v1=True)
        save_hubspot_config(db, org.id, {"access_token": "tok", "auto_sync_results_back": False})

        order = ServiceOrderService.create_order(
            db,
            org_id=org.id,
            user_id=user.id,
            service_code="survey",
            title="WA survey",
            config={},
        )
        recipient = ServiceOrderRecipient(
            order_id=order.id,
            row_number=1,
            name="Test User",
            email="test.user@example.com",
            phone="+447700900111",
            status="completed",
            result_json='{"analysis":{"sentiment":"positive","recommend_score":9}}',
        )
        db.add(recipient)
        db.commit()

        with patch(
            "app.services.hubspot_contact_sync_service._search_contact_by_email",
            return_value="hs-1001",
        ), patch("app.services.hubspot_contact_sync_service._update_hubspot_contact_properties"), patch(
            "app.services.hubspot_contact_sync_service._create_hubspot_note"
        ) as note_mock:
            result = sync_survey_result_to_hubspot(db, org.id, order=order, recipient=recipient, force=True)

        assert result["ok"] is True
        assert result["contact_id"] == "hs-1001"
        note_mock.assert_called_once()


def test_manual_push_endpoint(app_client):
    with get_sessionmaker()() as db:
        org, user = _seed_org_user(db)
        _enable_hubspot_platform(db, contact_sync_v1=True)
        save_hubspot_config(db, org.id, {"access_token": "tok", "auto_sync_results_back": True})

        order = ServiceOrderService.create_order(
            db,
            org_id=org.id,
            user_id=user.id,
            service_code="survey",
            title="WA survey",
            config={},
        )
        recipient = ServiceOrderRecipient(
            order_id=order.id,
            row_number=1,
            name="Test User",
            email="test.user@example.com",
            phone="+447700900111",
            status="completed",
            result_json='{"analysis":{"sentiment":"positive","recommend_score":9}}',
        )
        db.add(recipient)
        db.commit()
        headers = _auth_headers(app_client, org, user)

    with patch(
        "app.services.hubspot_contact_sync_service._search_contact_by_email",
        return_value="hs-1001",
    ), patch("app.services.hubspot_contact_sync_service._update_hubspot_contact_properties"), patch(
        "app.services.hubspot_contact_sync_service._create_hubspot_note"
    ):
        res = app_client.post(
            f"/service-orders/{order.id}/recipients/{recipient.id}/hubspot/sync-result",
            headers=headers,
        )

    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["contact_id"] == "hs-1001"


def test_maybe_sync_noops_for_non_survey():
    with get_sessionmaker()() as db:
        org, user = _seed_org_user(db)
        _enable_hubspot_platform(db, contact_sync_v1=True)
        order = ServiceOrderService.create_order(
            db,
            org_id=org.id,
            user_id=user.id,
            service_code="interview",
            title="Interview",
            config={},
        )
        recipient = ServiceOrderRecipient(
            order_id=order.id,
            row_number=1,
            name="Jane",
            email="jane@example.com",
            phone="+447700900123",
            status="completed",
        )
        db.add(recipient)
        db.commit()

        with patch("app.services.hubspot_contact_sync_service.sync_survey_result_to_hubspot") as sync_mock:
            maybe_sync_survey_result_to_hubspot(db, order, recipient)
        sync_mock.assert_not_called()
