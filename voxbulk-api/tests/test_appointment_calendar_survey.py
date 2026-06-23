"""Tests for appointment calendar sync and post-visit survey automation."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.appointment import Appointment
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.models.user import User
from app.services.appointment_availability_service import find_free_slots
from app.services.appointment_calendar_service import (
    calendar_status,
    get_busy_intervals,
    maybe_sync_appointment_calendar,
)
from app.services.appointment_post_survey_service import scan_post_visit_surveys, send_post_visit_survey
from app.services.appointment_settings_service import save_config
from app.services.scheduling_connection_service import save_scheduling_config


@pytest.fixture()
def db():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with get_sessionmaker()() as session:
        yield session


def _seed_org(db) -> tuple[Organisation, User]:
    org = Organisation(name="Calendar Appt Org")
    user = User(email=f"cal-appt-{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("pass"), is_active=True)
    db.add(org)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
    save_scheduling_config(
        db,
        org.id,
        {
            "provider": "google_calendar",
            "access_token": "google-access",
            "refresh_token": "google-refresh",
            "expires_at": (datetime.utcnow() + timedelta(hours=2)).isoformat(),
        },
    )
    save_config(
        db,
        org.id,
        {
            "calendar_enabled": True,
            "slot_duration_minutes": 30,
            "post_survey_enabled": True,
            "post_survey_delay_hours": 1,
        },
    )
    db.commit()
    return org, user


def _make_appt(db, org_id: str, *, when: datetime | None = None) -> Appointment:
    now = datetime.utcnow()
    appt = Appointment(
        id=str(uuid.uuid4()),
        org_id=org_id,
        contact_name="Jane Doe",
        contact_phone="+447700900123",
        contact_email="jane@example.com",
        appointment_datetime=when or (now + timedelta(days=2)),
        timezone="Europe/London",
        status="scheduled",
        crm_source="hubspot",
        crm_record_id="hs-1",
        created_at=now,
        updated_at=now,
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)
    return appt


def test_calendar_status_reports_google_api_ready(db):
    org, _user = _seed_org(db)
    status = calendar_status(db, org.id)
    assert status["calendar_enabled"] is True
    assert status["provider"] == "google_calendar"
    assert status["api_ready"] is True


@patch("app.services.appointment_calendar_service.httpx.Client")
def test_get_busy_intervals_google(mock_client_cls, db):
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_client.post.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "calendars": {
                "primary": {
                    "busy": [
                        {
                            "start": "2026-06-25T10:00:00Z",
                            "end": "2026-06-25T11:00:00Z",
                        }
                    ]
                }
            }
        },
    )

    org, _user = _seed_org(db)
    start = datetime(2026, 6, 25, 8, 0)
    end = datetime(2026, 6, 25, 18, 0)
    busy = get_busy_intervals(db, org.id, from_dt=start, to_dt=end)
    assert len(busy) == 1
    assert busy[0][0] == datetime(2026, 6, 25, 10, 0)


@patch("app.services.appointment_calendar_service.httpx.Client")
def test_maybe_sync_appointment_calendar_creates_event(mock_client_cls, db):
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_client.post.return_value = MagicMock(status_code=200, json=lambda: {"id": "evt-123"})

    org, _user = _seed_org(db)
    appt = _make_appt(db, org.id)
    result = maybe_sync_appointment_calendar(db, appt)
    db.commit()
    db.refresh(appt)
    assert result.get("ok") is True
    assert result.get("action") == "created"
    assert appt.calendar_event_id == "evt-123"


@patch("app.services.appointment_availability_service.get_busy_intervals", return_value=[(datetime(2026, 6, 25, 10, 0), datetime(2026, 6, 25, 11, 0))])
def test_find_free_slots_skips_calendar_busy(mock_busy, db):
    org, _user = _seed_org(db)
    from_dt = datetime(2026, 6, 25, 9, 0)
    slots = find_free_slots(db, org.id, from_dt=from_dt, days=1, limit=10)
    assert all(s.hour != 10 for s in slots)


@patch("app.services.survey_whatsapp_conversation_service.send_survey_opening", return_value=True)
def test_send_post_visit_survey_marks_sent(mock_opening, db):
    org, user = _seed_org(db)
    now = datetime.utcnow()
    order = ServiceOrder(
        id=str(uuid.uuid4()),
        org_id=org.id,
        user_id=user.id,
        service_code="survey",
        title="Post-visit feedback",
        status="running",
        config_json=json.dumps({"channels": ["whatsapp"], "whatsapp_flow": {"intro": "Hi"}}),
        created_at=now,
        updated_at=now,
    )
    db.add(order)
    db.commit()
    save_config(db, org.id, {"post_survey_order_id": order.id, "post_survey_enabled": True})
    appt = _make_appt(db, org.id, when=now - timedelta(hours=3))
    appt.status = "confirmed"
    db.add(appt)
    db.commit()
    result = send_post_visit_survey(db, appt)
    db.refresh(appt)
    assert result.get("ok") is True
    assert appt.post_survey_sent_at is not None
    mock_opening.assert_called_once()


@patch("app.services.appointment_post_survey_service.send_post_visit_survey")
def test_scan_post_visit_surveys_triggers_eligible(mock_send, db):
    mock_send.return_value = {"ok": True}
    org, _user = _seed_org(db)
    now = datetime.utcnow()
    appt = _make_appt(db, org.id, when=now - timedelta(hours=3))
    appt.status = "confirmed"
    db.add(appt)
    db.commit()
    result = scan_post_visit_surveys(db, org.id)
    assert result["sent"] == 1
    mock_send.assert_called_once()
