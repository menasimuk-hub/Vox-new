from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.core.database import get_sessionmaker
from app.models.appointment import Appointment
from app.models.call_log import CallLog
from app.models.organisation import Organisation
from app.services.appointment_tool_service import (
    build_initialization_response,
    tool_check_availability,
    tool_confirm_appointment,
    tool_reschedule_appointment,
)


@pytest.fixture()
def db():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with get_sessionmaker()() as session:
        yield session


def _org(db) -> Organisation:
    org = Organisation(id=str(uuid.uuid4()), name="Bright Dental", country="United Kingdom", deletion_status="active")
    org.appointment_manager_config_json = '{"workspace_name": "Bright Dental", "outreach_window_start": "09:00", "outreach_window_end": "17:00"}'
    db.add(org)
    db.commit()
    return org


def _appt(db, org: Organisation, *, hours_ahead: int = 48) -> Appointment:
    row = Appointment(
        id=str(uuid.uuid4()),
        org_id=org.id,
        contact_name="Jane Smith",
        contact_phone="+447700900123",
        appointment_datetime=datetime.utcnow() + timedelta(hours=hours_ahead),
        status="scheduled",
        crm_source="hubspot",
        crm_record_id="hs-123",
    )
    db.add(row)
    db.commit()
    return row


def test_initialization_injects_appointment_variables(db):
    org = _org(db)
    appt = _appt(db, org)
    db.add(
        CallLog(
            org_id=org.id,
            appointment_id=appt.id,
            provider="telnyx",
            external_call_id="call-live-1",
            direction="outbound",
            status="queued",
            to_number=appt.contact_phone,
            from_number="+442071234567",
            created_at=datetime.utcnow(),
        )
    )
    db.commit()
    out = build_initialization_response(
        db,
        {
            "data": {
                "event_type": "assistant.initialization",
                "payload": {"call_control_id": "call-live-1"},
            }
        },
    )
    vars_ = out["dynamic_variables"]
    assert vars_["appointment_id"] == appt.id
    assert vars_["company_name"] == "Bright Dental"
    assert "Jane" in vars_["first_name"]


def test_check_availability_returns_slots(db):
    org = _org(db)
    appt = _appt(db, org)
    result = tool_check_availability(db, {"arguments": {"appointment_id": appt.id}})
    assert result["status"] == "ok"
    assert len(result["slots"]) >= 1


def test_reschedule_and_confirm_update_appointment(db, monkeypatch):
    org = _org(db)
    appt = _appt(db, org)
    monkeypatch.setattr(
        "app.services.appointment_tool_service.maybe_writeback_appointment_to_crm",
        lambda _db, _appt: {"ok": True},
    )
    slots = tool_check_availability(db, {"arguments": {"appointment_id": appt.id}})
    rescheduled = tool_reschedule_appointment(
        db,
        {"arguments": {"appointment_id": appt.id, "slot_index": 0, "slot_iso": slots["slots"][0]["iso"]}},
    )
    assert rescheduled["status"] == "ok"
    db.refresh(appt)
    assert appt.status == "rescheduled"
    assert appt.rescheduled_to_datetime is not None

    confirmed = tool_confirm_appointment(db, {"arguments": {"appointment_id": appt.id}})
    assert confirmed["status"] == "ok"
    db.refresh(appt)
    assert appt.status == "confirmed"
