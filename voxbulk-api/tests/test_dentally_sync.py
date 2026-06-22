def test_dentally_missing_config_fails_safely(app_client):
    from app.workers.sync_tasks import dentally_sync_tenant

    res = dentally_sync_tenant.delay(org_id="org")
    out = res.get()
    assert out["ok"] is False


def test_dentally_sync_idempotent_and_tenant_safe(app_client, monkeypatch):
    import os

    os.environ["DENTALLY_API_KEY"] = "test-key"

    from app.services.dentally import DentallyAdapter

    def fake_list_branches(self):
        return [{"id": "b1", "name": "Branch 1"}]

    def fake_list_patients(self):
        return [{"id": "p1", "first_name": "A", "last_name": "B", "phone_e164": "+447000000001"}]

    def fake_list_appointments(self):
        return [
            {
                "id": "a1",
                "scheduled_start": "2026-05-05T10:00:00Z",
                "status": "scheduled",
                "patient_id": "p1",
                "branch_id": "b1",
                "reason": "Check-up",
                "treatment_description": "Hygiene appointment",
            }
        ]

    monkeypatch.setattr(DentallyAdapter, "list_branches", fake_list_branches, raising=True)
    monkeypatch.setattr(DentallyAdapter, "list_patients", fake_list_patients, raising=True)
    monkeypatch.setattr(DentallyAdapter, "list_appointments", fake_list_appointments, raising=True)

    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation
    from app.models.branch import Branch
    from app.models.patient import Patient
    from app.models.dentally_appointment import DentallyAppointment
    from sqlalchemy import func, select

    with get_sessionmaker()() as db:
        org = Organisation(name="Org")
        db.add(org)
        db.commit()
        org_id = org.id

    from app.workers.sync_tasks import dentally_sync_tenant

    r1 = dentally_sync_tenant.delay(org_id=org_id).get()
    assert r1["ok"] is True
    assert r1["branches"]["created"] == 1

    r2 = dentally_sync_tenant.delay(org_id=org_id).get()
    assert r2["ok"] is True

    with get_sessionmaker()() as db:
        assert db.execute(select(func.count()).select_from(Branch)).scalar_one() == 1
        assert db.execute(select(func.count()).select_from(Patient)).scalar_one() == 1
        assert db.execute(select(func.count()).select_from(DentallyAppointment)).scalar_one() == 1
        appt = db.execute(select(DentallyAppointment).limit(1)).scalar_one()
        assert appt.treatment_label == "Hygiene appointment"

    # tenant-safe: syncing for a second org creates separate rows
    with get_sessionmaker()() as db:
        org2 = Organisation(name="Org2")
        db.add(org2)
        db.commit()
        org2_id = org2.id

    dentally_sync_tenant.delay(org_id=org2_id).get()
    with get_sessionmaker()() as db:
        assert db.execute(select(func.count()).select_from(Branch)).scalar_one() == 2


def test_multichannel_fallback_to_whatsapp(app_client, monkeypatch):
    from app.services import telnyx_messaging_service, telnyx_voice_service
    from app.services.provider_settings import ProviderSettingsService
    from app.services.telnyx_messaging_service import TelnyxMessageResult
    from app.services.telnyx_voice_service import TelnyxProviderResult

    def fake_start_outbound_call(**kwargs):
        return TelnyxProviderResult(ok=False, status="failed", detail="call failed")

    def fake_send_survey_message(db, *, org_id, to_number, body, prefer_whatsapp=True):
        return TelnyxMessageResult(ok=True, status="queued", external_id="msg-test-123", channel="whatsapp")

    telnyx_voice_service.TelnyxVoiceAdapter.start_outbound_call = staticmethod(fake_start_outbound_call)
    monkeypatch.setattr(telnyx_messaging_service.TelnyxMessagingService, "send_survey_message", staticmethod(fake_send_survey_message))
    monkeypatch.setattr("app.workers.call_tasks.is_within_calling_window", lambda _now: True)

    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation
    from app.models.user import User
    from app.models.membership import OrganisationMembership
    from app.models.patient import Patient
    from app.models.dentally_appointment import DentallyAppointment
    from datetime import datetime, timezone
    from app.core.security import hash_password

    with get_sessionmaker()() as db:
        org = Organisation(name="MC")
        db.add(org)
        db.flush()
        user = User(email="mc@example.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        patient = Patient(org_id=org.id, first_name="A", last_name="B", phone_e164="+447000000001")
        db.add(patient)
        db.flush()
        appt = Appointment(org_id=org.id, patient_id=patient.id, scheduled_start=datetime.now(timezone.utc))
        db.add(appt)
        ProviderSettingsService.upsert_platform_config(
            db,
            provider="telnyx",
            is_enabled=True,
            config={
                "api_key": "KEY0123456789012345678901234567890123456789012345678901234567890",
                "connection_id": "conn-test",
                "default_outbound_number": "+447000000000",
                "fallback_caller_id": "+447000000000",
                "media_stream_url": "wss://example.com/telnyx/media-stream",
                "webhook_base_url": "https://example.com",
            },
        )
        db.commit()

    tok = app_client.post("/auth/token", data={"username": "mc@example.com", "password": "pass123", "org_id": org.id}).json()["access_token"]
    r = app_client.post(f"/dentally/appointments/{appt.id}/recovery", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    job_id = r.json()["job_id"]

    st = app_client.get(f"/calls/recovery/jobs/{job_id}", headers={"Authorization": f"Bearer {tok}"}).json()
    assert st["state"] == "messaged"
