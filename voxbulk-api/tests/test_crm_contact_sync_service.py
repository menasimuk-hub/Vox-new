"""Tests for unified CRM contact sync facade."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.test_wave2_crm_integrations import _seed_org


@pytest.fixture()
def session(app_client):  # noqa: ARG001
    from app.core.database import get_sessionmaker

    Session = get_sessionmaker()
    db = Session()
    try:
        yield db
    finally:
        db.close()


def test_crm_sync_status_no_provider(session):
    from app.services.crm_contact_sync_service import crm_sync_status

    org = _seed_org(session)
    result = crm_sync_status(session, org.id)
    assert result["provider"] is None
    assert result["connected"] is False


def test_crm_sync_status_pipedrive_connected(session):
    from app.services.crm_connection_service import save_crm_config_raw
    from app.services.crm_contact_sync_service import crm_sync_status

    org = _seed_org(session)
    save_crm_config_raw(session, org.id, "pipedrive", {"access_token": "tok", "connected_at": "2026-01-01"})
    result = crm_sync_status(session, org.id)
    assert result["provider"] == "pipedrive"
    assert result["connected"] is True
    assert result["sync_settings_enabled"] is True


def test_import_requires_active_crm(session):
    from app.services.crm_contact_sync_service import CrmContactSyncError, import_contacts_to_order

    org = _seed_org(session)
    with pytest.raises(CrmContactSyncError, match="Connect a CRM"):
        import_contacts_to_order(session, org.id, order_id="ord-1", contact_ids=["c1"])


def test_maybe_sync_survey_result_pipedrive(session):
    from app.models.service_order import ServiceOrder, ServiceOrderRecipient
    from app.services.crm_connection_service import save_crm_config_raw
    from app.services.crm_survey_result_sync_service import maybe_sync_survey_result_to_active_crm

    org = _seed_org(session)
    save_crm_config_raw(
        session,
        org.id,
        "pipedrive",
        {"access_token": "tok", "auto_sync_results_back": False},
    )
    order = ServiceOrder(org_id=org.id, service_code="survey", title="T")
    order.id = "ord-1"
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="A",
        phone="+447700900123",
        status="completed",
    )
    recipient.id = "rec-1"
    with patch("app.services.pipedrive_contact_sync_service.sync_survey_result_to_pipedrive") as sync_mock:
        sync_mock.return_value = {"ok": True, "skipped": True, "reason": "auto_sync_disabled"}
        maybe_sync_survey_result_to_active_crm(session, order, recipient)
        sync_mock.assert_called_once()
