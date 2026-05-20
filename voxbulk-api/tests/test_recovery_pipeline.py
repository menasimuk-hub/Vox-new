from app.core.security import hash_password


def _seed(db):
    from datetime import datetime, timezone

    from app.models.appointment import Appointment
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.patient import Patient
    from app.models.user import User
    from app.services.provider_settings import ProviderSettingsService

    org = Organisation(name="Recovery Org")
    db.add(org)
    db.flush()
    user = User(email="recovery@example.com", password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
    patient = Patient(org_id=org.id, first_name="A", last_name="B", phone_e164="+447000000001")
    db.add(patient)
    db.flush()
    appt = Appointment(org_id=org.id, patient_id=patient.id, scheduled_start=datetime.now(timezone.utc), status="scheduled")
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
    return user, org, appt


def test_enqueue_recovery_and_poll_status(app_client, monkeypatch):
    from app.services import telnyx_voice_service

    monkeypatch.setattr("app.workers.call_tasks.is_within_calling_window", lambda _now: True)

    def _fake_start_outbound_call(**kwargs):
        from app.services.telnyx_voice_service import TelnyxProviderResult

        return TelnyxProviderResult(ok=True, status="initiated", external_id="v3:test-call-123")

    telnyx_voice_service.TelnyxVoiceAdapter.start_outbound_call = staticmethod(_fake_start_outbound_call)

    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org, appt = _seed(db)

    tok = app_client.post("/auth/token", data={"username": user.email, "password": "pass123", "org_id": org.id}).json()[
        "access_token"
    ]
    headers = {"Authorization": f"Bearer {tok}"}

    r = app_client.post(f"/appointments/{appt.id}/recovery", headers=headers)
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    task_id = r.json()["task_id"]

    st = app_client.get(f"/calls/recovery/jobs/{job_id}", headers=headers)
    assert st.status_code == 200
    assert st.json()["state"] in {"calling", "failed", "skipped", "queued", "messaged"}

    ts = app_client.get(f"/calls/recovery/tasks/{task_id}", headers=headers)
    assert ts.status_code == 200
    assert ts.json()["task_id"] == task_id


def test_telnyx_callback_updates_states(app_client):
    from datetime import datetime, timezone
    from app.core.database import get_sessionmaker
    from app.models.appointment import Appointment
    from app.models.organisation import Organisation
    from app.models.user import User
    from app.models.membership import OrganisationMembership
    from app.models.patient import Patient
    from app.models.recovery_job import RecoveryJob

    with get_sessionmaker()() as db:
        org = Organisation(name="Org")
        db.add(org)
        db.flush()
        user = User(email="cb@example.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        patient = Patient(org_id=org.id, first_name="A", last_name="B", phone_e164="+447000000001")
        db.add(patient)
        db.flush()
        appt = Appointment(
            org_id=org.id,
            patient_id=patient.id,
            scheduled_start=datetime.now(timezone.utc),
            status="scheduled",
            recovery_state="calling",
        )
        db.add(appt)
        db.flush()
        job = RecoveryJob(
            org_id=org.id,
            appointment_id=appt.id,
            idempotency_key=f"appointment:{appt.id}",
            provider="telnyx",
            provider_ref="v3:test-call-123",
            state="calling",
        )
        db.add(job)
        db.commit()

    tok = app_client.post("/auth/token", data={"username": "cb@example.com", "password": "pass123", "org_id": org.id}).json()[
        "access_token"
    ]
    payload = {
        "data": {
            "event_type": "call.hangup",
            "payload": {
                "call_control_id": "v3:test-call-123",
                "call_status": "completed",
                "client_state": "",
            },
        }
    }
    r = app_client.post("/telnyx/webhooks/status", json=payload, headers={"X-Retover-Org-Id": org.id})
    assert r.status_code == 200

    headers = {"Authorization": f"Bearer {tok}"}
    st = app_client.get(f"/calls/recovery/jobs/{job.id}", headers=headers).json()
    assert st["state"] == "messaged"


def test_telnyx_out_of_order_callback_does_not_regress(app_client):
    from datetime import datetime, timezone
    from app.core.database import get_sessionmaker
    from app.models.appointment import Appointment
    from app.models.organisation import Organisation
    from app.models.user import User
    from app.models.membership import OrganisationMembership
    from app.models.patient import Patient
    from app.models.recovery_job import RecoveryJob

    with get_sessionmaker()() as db:
        org = Organisation(name="Org2")
        db.add(org)
        db.flush()
        user = User(email="cb2@example.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        patient = Patient(org_id=org.id, first_name="A", last_name="B", phone_e164="+447000000001")
        db.add(patient)
        db.flush()
        appt = Appointment(
            org_id=org.id,
            patient_id=patient.id,
            scheduled_start=datetime.now(timezone.utc),
            status="scheduled",
            recovery_state="calling",
        )
        db.add(appt)
        db.flush()
        job = RecoveryJob(
            org_id=org.id,
            appointment_id=appt.id,
            idempotency_key=f"appointment:{appt.id}",
            provider="telnyx",
            provider_ref="v3:test-call-999",
            state="calling",
        )
        db.add(job)
        db.commit()

    tok = app_client.post("/auth/token", data={"username": "cb2@example.com", "password": "pass123", "org_id": org.id}).json()[
        "access_token"
    ]
    headers = {"Authorization": f"Bearer {tok}"}

    completed = {
        "data": {
            "event_type": "call.hangup",
            "payload": {"call_control_id": "v3:test-call-999", "call_status": "completed"},
        }
    }
    r1 = app_client.post("/telnyx/webhooks/status", json=completed, headers={"X-Retover-Org-Id": org.id})
    assert r1.status_code == 200

    ringing = {
        "data": {
            "event_type": "call.initiated",
            "payload": {"call_control_id": "v3:test-call-999", "call_status": "ringing"},
        }
    }
    r2 = app_client.post("/telnyx/webhooks/status", json=ringing, headers={"X-Retover-Org-Id": org.id})
    assert r2.status_code == 200

    st = app_client.get(f"/calls/recovery/jobs/{job.id}", headers=headers).json()
    assert st["state"] == "messaged"


def test_recovery_state_transitions_are_safe(app_client):
    from datetime import datetime, timezone

    from app.core.database import get_sessionmaker
    from app.models.appointment import Appointment
    from app.services.recovery_service import RecoveryStateMachine

    with get_sessionmaker()() as db:
        appt = Appointment(org_id="o", scheduled_start=datetime.now(timezone.utc), status="scheduled")
        db.add(appt)
        db.commit()
        db.refresh(appt)

        RecoveryStateMachine.transition(db, appointment=appt, to_state="queued")
        db.commit()

        try:
            RecoveryStateMachine.transition(db, appointment=appt, to_state="recovered")
            assert False, "expected ValueError"
        except ValueError:
            pass
