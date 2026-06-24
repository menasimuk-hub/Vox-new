from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.core.database import get_engine, get_sessionmaker
from app.core.security import hash_password
from app.models.appointment import Appointment
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.appointment_crm_writeback_service import maybe_writeback_appointment_to_crm
from app.services.appointment_settings_service import save_config
from app.services.hubspot_connection_service import save_hubspot_config


def setup_function(_func):
    from app.core.database import Base
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_org(db):
    org = Organisation(name="HubSpot Writeback Org")
    user = User(email=f"hs-writeback-{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("pass"), is_active=True)
    db.add(org)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
    save_hubspot_config(db, org.id, {"access_token": "tok-writeback", "hub_id": "42"})
    return org


def _seed_appointment(db, *, org_id: str, status: str, crm_record_id: str) -> Appointment:
    now = datetime.utcnow()
    appt = Appointment(
        id=str(uuid.uuid4()),
        org_id=org_id,
        contact_name="Patient Test",
        contact_phone="+447700900777",
        contact_email="patient@example.com",
        appointment_datetime=now + timedelta(days=1),
        timezone="Europe/London",
        status=status,
        crm_source="hubspot",
        crm_record_id=crm_record_id,
        created_at=now,
        updated_at=now,
    )
    if status == "rescheduled":
        appt.rescheduled_to_datetime = now + timedelta(days=2)
    db.add(appt)
    db.commit()
    db.refresh(appt)
    return appt


@patch("app.services.appointment_crm_writeback_service._hubspot_property_exists", return_value=True)
@patch("app.services.appointment_crm_writeback_service._maybe_move_hubspot_lists")
@patch("app.services.hubspot_connection_service._ensure_access_token", return_value="tok-writeback")
@patch("app.services.hubspot_connection_service.hubspot_status", return_value={"connected": True})
@patch("app.services.appointment_crm_writeback_service.httpx.Client")
def test_writeback_contacts_updates_contact_and_lists(
    client_cls,
    _status_m,
    _token_m,
    list_move_m,
    _prop_exists_m,
):
    with get_sessionmaker()() as db:
        org = _seed_org(db)
        save_config(db, org.id, {"crm_object": "contacts", "crm_date_property": "appointment_date"})
        appt = _seed_appointment(db, org_id=org.id, status="confirmed", crm_record_id="contacts:hs-contact-1")

        client = client_cls.return_value.__enter__.return_value
        client.patch.return_value = MagicMock(status_code=200, text="ok")
        result = maybe_writeback_appointment_to_crm(db, appt)

        assert result.get("ok") is True
        assert result.get("crm_object") == "contacts"
        called_url = str(client.patch.call_args.args[0])
        assert "/crm/v3/objects/contacts/hs-contact-1" in called_url
        assert list_move_m.called


@patch("app.services.appointment_crm_writeback_service._hubspot_property_exists", return_value=True)
@patch("app.services.appointment_crm_writeback_service._maybe_move_hubspot_lists")
@patch("app.services.hubspot_connection_service._ensure_access_token", return_value="tok-writeback")
@patch("app.services.hubspot_connection_service.hubspot_status", return_value={"connected": True})
@patch("app.services.appointment_crm_writeback_service.httpx.Client")
def test_writeback_deals_updates_object_without_list_moves(
    client_cls,
    _status_m,
    _token_m,
    list_move_m,
    _prop_exists_m,
):
    with get_sessionmaker()() as db:
        org = _seed_org(db)
        save_config(db, org.id, {"crm_object": "deals", "crm_date_property": "appointment_date"})
        appt = _seed_appointment(db, org_id=org.id, status="rescheduled", crm_record_id="deals:deal-99")

        client = client_cls.return_value.__enter__.return_value
        client.patch.return_value = MagicMock(status_code=200, text="ok")
        result = maybe_writeback_appointment_to_crm(db, appt)

        assert result.get("ok") is True
        assert result.get("crm_object") == "deals"
        called_url = str(client.patch.call_args.args[0])
        assert "/crm/v3/objects/deals/deal-99" in called_url
        list_move_m.assert_not_called()


@patch("app.services.appointment_crm_writeback_service._hubspot_property_exists", return_value=False)
@patch("app.services.hubspot_connection_service._ensure_access_token", return_value="tok-writeback")
@patch("app.services.hubspot_connection_service.hubspot_status", return_value={"connected": True})
def test_writeback_skips_when_no_matching_properties(
    _status_m,
    _token_m,
    _prop_exists_m,
):
    with get_sessionmaker()() as db:
        org = _seed_org(db)
        save_config(db, org.id, {"crm_object": "deals", "crm_date_property": "appointment_date"})
        appt = _seed_appointment(db, org_id=org.id, status="confirmed", crm_record_id="deals:deal-101")
        result = maybe_writeback_appointment_to_crm(db, appt)

        assert result.get("skipped") is True
        assert result.get("reason") == "no_writable_properties"
