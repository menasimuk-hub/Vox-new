from __future__ import annotations
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest
from app.core.database import get_sessionmaker
from app.models.agent import AgentDefinition
from app.models.appointment import Appointment
from app.models.organisation import Organisation
from app.services.appointment_call_service import handle_appointment_telnyx_event
from app.services.appointment_voice_agent_service import build_appointment_opening_greeting, build_appointment_voice_config

@pytest.fixture()
def db():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with get_sessionmaker()() as session:
        yield session

def _seed_org(db, name="Acme Clinic"):
    org = Organisation(id=str(uuid.uuid4()), name=name, country="United Kingdom", deletion_status="active")
    db.add(org)
    db.commit()
    return org

def _seed_agent(db):
    agent = AgentDefinition(
        id=str(uuid.uuid4()), name="appointment_GB-Emily", slug="appointment-gb-emily-test",
        description="test", system_prompt="You are Emily.", supports_appointment=True,
        is_default_appointment=True, disclosure_for_appointment=True, voice_label="Emily",
        telnyx_assistant_id="assistant-test-emily",
        opening_disclosure_template="Hello {first_name}, this is {agent_name} from {company_name} about your appointment on {appointment_datetime}.",
        is_active=True, created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db.add(agent)
    db.commit()
    return agent

def test_build_appointment_voice_config_uses_workspace_name(db):
    org = _seed_org(db)
    org.appointment_manager_config_json = '{"workspace_name": "Bright Dental"}'
    db.add(org)
    db.commit()
    appt = Appointment(id=str(uuid.uuid4()), org_id=org.id, contact_name="Jane Smith", contact_phone="+447700900123", appointment_datetime=datetime(2026, 7, 15, 14, 30), status="scheduled", crm_source="manual")
    cfg = build_appointment_voice_config(db, appt=appt, call_kind="confirmation")
    assert cfg["company_name"] == "Bright Dental"
    assert "July" in cfg["appointment_datetime"]

def test_build_appointment_opening_greeting(db):
    org = _seed_org(db)
    org.appointment_manager_config_json = '{"workspace_name": "Bright Dental"}'
    db.add(org)
    db.commit()
    agent = _seed_agent(db)
    appt = Appointment(id=str(uuid.uuid4()), org_id=org.id, contact_name="Jane Smith", contact_phone="+447700900123", appointment_datetime=datetime(2026, 7, 15, 14, 30), status="scheduled", crm_source="manual")
    voice_cfg = build_appointment_voice_config(db, appt=appt, call_kind="confirmation")
    greeting = build_appointment_opening_greeting(db, appt=appt, agent=agent, config=voice_cfg)
    assert "Jane" in greeting
    assert "Bright Dental" in greeting
    assert "Emily" in greeting

def test_handle_appointment_telnyx_event_starts_assistant_on_answered(db):
    org = _seed_org(db)
    agent = _seed_agent(db)
    appt = Appointment(id=str(uuid.uuid4()), org_id=org.id, contact_name="Jane Smith", contact_phone="+447700900123", appointment_datetime=datetime(2026, 7, 15, 14, 30), status="scheduled", crm_source="manual")
    db.add(appt)
    db.commit()
    import base64, json
    client_state = base64.b64encode(json.dumps({"appointment_call": True, "appointment_id": appt.id, "org_id": org.id, "agent_id": agent.id, "telnyx_assistant_id": agent.telnyx_assistant_id, "call_kind": "confirmation"}).encode()).decode()
    with patch("app.services.appointment_call_service._telnyx_config", return_value={"api_key": "k", "connection_id": "c"}), patch("app.services.appointment_call_service.TelnyxVoiceAdapter.start_ai_assistant") as start_mock:
        start_mock.return_value = MagicMock(ok=True, status="assistant_started", detail=None)
        handled = handle_appointment_telnyx_event(db, {"data": {"event_type": "call.answered", "payload": {"call_control_id": "call-123", "client_state": client_state, "result": "human"}}})
    assert handled is True
    start_mock.assert_called_once()
