"""Tests for HubSpot list service and list-based appointment sync."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.appointment_crm_sync_service import _fetch_hubspot_appointments
from app.services.appointment_settings_service import save_config
from app.services.hubspot_connection_service import save_hubspot_config
from app.services.hubspot_list_service import (
    batch_read_contacts,
    fetch_list_member_record_ids,
    list_hubspot_lists,
    move_contact_between_lists,
)


def _seed_org(db) -> Organisation:
    org = Organisation(name="List Sync Org")
    user = User(email=f"hs-list-{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("pass"), is_active=True)
    db.add(org)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
    save_hubspot_config(
        db,
        org.id,
        {
            "access_token": "tok-list",
            "hub_id": "99",
            "appointment_list_id": "list-appt-1",
        },
    )
    save_config(db, org.id, {"crm_date_property": "appointment_date"})
    db.commit()
    return org


def test_list_hubspot_lists_parses_search_response():
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {
        "lists": [
            {"listId": "101", "name": "VoxBulk Appointments", "processingType": "MANUAL", "size": 2},
        ]
    }
    with patch("app.services.hubspot_list_service.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.post.return_value = mock_res
        items = list_hubspot_lists("tok", limit=10)
    assert len(items) == 1
    assert items[0]["id"] == "101"
    assert items[0]["name"] == "VoxBulk Appointments"


def test_fetch_list_member_record_ids_paginates():
    first = MagicMock(status_code=200)
    first.json.return_value = {
        "results": [{"recordId": "1"}, {"recordId": "2"}],
        "paging": {"next": {"after": "cursor-2"}},
    }
    second = MagicMock(status_code=200)
    second.json.return_value = {"results": [{"recordId": "3"}], "paging": {}}
    with patch("app.services.hubspot_list_service.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.side_effect = [first, second]
        ids = fetch_list_member_record_ids("tok", "list-1")
    assert ids == ["1", "2", "3"]


def test_batch_read_contacts():
    mock_res = MagicMock(status_code=200)
    mock_res.json.return_value = {
        "results": [
            {
                "id": "1",
                "properties": {
                    "firstname": "Sara",
                    "lastname": "Patel",
                    "phone": "+447700900123",
                    "appointment_date": "2026-06-25T10:00:00Z",
                },
            }
        ]
    }
    with patch("app.services.hubspot_list_service.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.post.return_value = mock_res
        rows = batch_read_contacts("tok", ["1"], ["firstname", "phone", "appointment_date"])
    assert rows[0]["id"] == "1"


def test_fetch_hubspot_appointments_from_list():
    tomorrow = (datetime.utcnow() + timedelta(days=1)).replace(microsecond=0)
    appt_iso = tomorrow.isoformat() + "Z"
    with get_sessionmaker()() as db:
        org = _seed_org(db)
        with (
            patch("app.services.hubspot_connection_service.hubspot_status", return_value={"connected": True}),
            patch("app.services.hubspot_connection_service._ensure_access_token", return_value="tok-list"),
            patch(
                "app.services.hubspot_list_service.fetch_list_contacts",
                return_value=[
                    {
                        "id": "hs-1",
                        "properties": {
                            "firstname": "Sara",
                            "lastname": "Patel",
                            "phone": "+447700900123",
                            "email": "sara@test.com",
                            "appointment_date": appt_iso,
                        },
                    }
                ],
            ),
        ):
            rows = _fetch_hubspot_appointments(db, org.id)
        assert len(rows) == 1
        assert rows[0].crm_record_id == "hs-1"
        assert rows[0].contact_phone == "+447700900123"


def test_move_contact_between_lists_calls_add_and_remove():
    with patch("app.services.hubspot_list_service.remove_contacts_from_list") as remove_m, patch(
        "app.services.hubspot_list_service.add_contacts_to_list"
    ) as add_m:
        move_contact_between_lists(
            "tok",
            contact_id="42",
            remove_from_list_id="src",
            add_to_list_id="dst",
        )
        remove_m.assert_called_once_with("tok", "src", ["42"])
        add_m.assert_called_once_with("tok", "dst", ["42"])
