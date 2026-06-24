from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.core.database import get_engine, get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.appointment_crm_sync_service import _fetch_pipedrive_appointments, _fetch_zoho_appointments
from app.services.appointment_settings_service import save_config


def setup_function(_func):
    from app.core.database import Base
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_org(db) -> Organisation:
    org = Organisation(name="CRM Appointment Sync Org")
    user = User(email=f"crm-sync-{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("pass"), is_active=True)
    db.add(org)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
    db.commit()
    db.refresh(org)
    return org


@patch("app.services.pipedrive_connection_service._ensure_access_token", return_value="tok-pd")
@patch("app.services.pipedrive_connection_service.pipedrive_status", return_value={"connected": True})
@patch("app.services.appointment_crm_sync_service.httpx.Client")
def test_fetch_pipedrive_appointments_uses_mapping(client_cls, _status_m, _token_m):
    with get_sessionmaker()() as db:
        org = _seed_org(db)
        save_config(
            db,
            org.id,
            {
                "crm_date_property": "next_meeting_at",
                "crm_phone_property": "custom_phone_prop",
                "crm_name_property": "custom_name_prop",
            },
        )
        when = (datetime.utcnow() + timedelta(days=1)).replace(microsecond=0).isoformat() + "Z"
        deal_res = MagicMock(status_code=200)
        deal_res.json.return_value = {
            "data": [
                {
                    "id": 3001,
                    "title": "Dental consult",
                    "next_meeting_at": when,
                    "custom_phone_prop": "+447700911001",
                    "custom_name_prop": "Patient PD",
                    "stage_name": "Booked",
                }
            ]
        }
        client = client_cls.return_value.__enter__.return_value
        client.get.return_value = deal_res
        rows = _fetch_pipedrive_appointments(db, org.id)

        assert len(rows) == 1
        assert rows[0].crm_source == "pipedrive"
        assert rows[0].crm_record_id == "3001"
        assert rows[0].contact_name == "Patient PD"
        assert rows[0].contact_phone == "+447700911001"
        assert rows[0].branch == "Booked"


@patch("app.services.zoho_crm_connection_service._ensure_access_token", return_value=("tok-zoho", "www.zohoapis.com"))
@patch("app.services.zoho_crm_connection_service.zoho_crm_status", return_value={"connected": True})
@patch("app.services.appointment_crm_sync_service.httpx.Client")
def test_fetch_zoho_appointments_uses_mapping(client_cls, _status_m, _token_m):
    with get_sessionmaker()() as db:
        org = _seed_org(db)
        save_config(
            db,
            org.id,
            {
                "crm_date_property": "Appointment_Date__c",
                "crm_phone_property": "Phone_Custom__c",
                "crm_name_property": "Patient_Name__c",
            },
        )
        when = (datetime.utcnow() + timedelta(days=2)).replace(microsecond=0).isoformat() + "Z"
        zoho_res = MagicMock(status_code=200)
        zoho_res.json.return_value = {
            "data": [
                {
                    "id": "z-5001",
                    "Deal_Name": "Consultation",
                    "Appointment_Date__c": when,
                    "Phone_Custom__c": "+447700922002",
                    "Patient_Name__c": "Patient Zoho",
                    "Stage": "Confirmed",
                    "Email": "zoho.patient@example.com",
                }
            ]
        }
        client = client_cls.return_value.__enter__.return_value
        client.get.return_value = zoho_res
        rows = _fetch_zoho_appointments(db, org.id)

        assert len(rows) == 1
        assert rows[0].crm_source == "zoho_crm"
        assert rows[0].crm_record_id == "z-5001"
        assert rows[0].contact_name == "Patient Zoho"
        assert rows[0].contact_phone == "+447700922002"
        assert rows[0].contact_email == "zoho.patient@example.com"
        assert rows[0].branch == "Confirmed"
