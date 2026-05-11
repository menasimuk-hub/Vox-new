from app.core.security import compute_twilio_signature, hash_password


def _seed(db):
    from datetime import datetime, timezone

    from app.models.appointment import Appointment
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.patient import Patient
    from app.models.user import User

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
    db.commit()
    return user, org, appt


def test_enqueue_recovery_and_poll_status(app_client):
    # Configure Twilio credentials and patch network call.
    import os
    from app.services import twilio_service

    os.environ["TWILIO_ACCOUNT_SID"] = "ACxxx"
    os.environ["TWILIO_API_KEY"] = "SKxxx"
    os.environ["TWILIO_API_SECRET"] = "secret"
    os.environ["TWILIO_FROM_NUMBER"] = "+447000000000"
    os.environ["TWILIO_TWIML_URL"] = "https://example.com/twiml.xml"
    os.environ["TWILIO_WHATSAPP_FROM"] = "whatsapp:+447000000000"

    def _fake_create_call(*, to_number: str, from_number: str, twiml_url: str) -> dict:
        return {"sid": "CA123"}

    def _fake_create_call2(*, account_sid: str, api_key: str, api_secret: str, to_number: str, from_number: str, twiml_url: str) -> dict:
        return {"sid": "CA123"}

    twilio_service.TwilioAdapter._create_call = staticmethod(_fake_create_call2)

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

    # eager celery processes immediately in tests
    st = app_client.get(f"/calls/recovery/jobs/{job_id}", headers=headers)
    assert st.status_code == 200
    assert st.json()["state"] in {"calling", "failed", "skipped", "queued", "messaged"}

    ts = app_client.get(f"/calls/recovery/tasks/{task_id}", headers=headers)
    assert ts.status_code == 200
    assert ts.json()["task_id"] == task_id


def test_duplicate_webhook_is_idempotent(app_client):
    url = "http://testserver/webhooks/twilio"
    sig = compute_twilio_signature(auth_token="twilio-test-auth-token", url=url, params={"foo": "bar"})

    r1 = app_client.post("/webhooks/twilio", data={"foo": "bar"}, headers={"X-Twilio-Signature": sig})
    assert r1.status_code == 200
    r2 = app_client.post("/webhooks/twilio", data={"foo": "bar"}, headers={"X-Twilio-Signature": sig})
    assert r2.status_code == 200

    # Only one persisted webhook event for same payload/provider
    from app.core.database import get_sessionmaker
    from app.models.webhook_event import WebhookEvent
    from sqlalchemy import select, func

    with get_sessionmaker()() as db:
        cnt = db.execute(select(func.count()).select_from(WebhookEvent).where(WebhookEvent.provider == "twilio")).scalar_one()
    assert int(cnt) == 1


def test_twilio_duplicate_status_callback_is_idempotent(app_client):
    url = "http://testserver/webhooks/twilio"
    params = {"CallSid": "CA777", "CallStatus": "completed"}
    sig = compute_twilio_signature(auth_token="twilio-test-auth-token", url=url, params=params)

    r1 = app_client.post("/webhooks/twilio", data=params, headers={"X-Twilio-Signature": sig})
    assert r1.status_code == 200
    r2 = app_client.post("/webhooks/twilio", data=params, headers={"X-Twilio-Signature": sig})
    assert r2.status_code == 200

    from app.core.database import get_sessionmaker
    from app.models.webhook_event import WebhookEvent
    from sqlalchemy import func, select

    with get_sessionmaker()() as db:
        cnt = db.execute(
            select(func.count())
            .select_from(WebhookEvent)
            .where(WebhookEvent.provider == "twilio", WebhookEvent.external_event_id == "CA777:completed")
        ).scalar_one()
    assert int(cnt) == 1


def test_twilio_callback_updates_states(app_client):
    # Seed a recovery job with known CallSid, then send a callback and verify state transitions.
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
        db.add(org); db.flush()
        user = User(email="cb@example.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(user); db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        patient = Patient(org_id=org.id, first_name="A", last_name="B", phone_e164="+447000000001")
        db.add(patient); db.flush()
        appt = Appointment(org_id=org.id, patient_id=patient.id, scheduled_start=datetime.now(timezone.utc), status="scheduled", recovery_state="calling")
        db.add(appt); db.flush()
        job = RecoveryJob(org_id=org.id, appointment_id=appt.id, idempotency_key=f"appointment:{appt.id}", provider="twilio", provider_ref="CA123", state="calling")
        db.add(job); db.commit()

    tok = app_client.post("/auth/token", data={"username": "cb@example.com", "password": "pass123", "org_id": org.id}).json()["access_token"]
    # callback is unauthenticated; just needs Twilio signature
    url = "http://testserver/webhooks/twilio"
    params = {"CallSid": "CA123", "CallStatus": "completed"}
    sig = compute_twilio_signature(auth_token="twilio-test-auth-token", url=url, params=params)
    r = app_client.post("/webhooks/twilio", data=params, headers={"X-Twilio-Signature": sig})
    assert r.status_code == 200

    # tenant can inspect updated state
    headers = {"Authorization": f"Bearer {tok}"}
    st = app_client.get(f"/calls/recovery/jobs/{job.id}", headers=headers).json()
    assert st["state"] == "messaged"


def test_twilio_out_of_order_callback_does_not_regress(app_client):
    # completed then ringing should not regress from messaged->calling
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
        db.add(org); db.flush()
        user = User(email="cb2@example.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(user); db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        patient = Patient(org_id=org.id, first_name="A", last_name="B", phone_e164="+447000000001")
        db.add(patient); db.flush()
        appt = Appointment(org_id=org.id, patient_id=patient.id, scheduled_start=datetime.now(timezone.utc), status="scheduled", recovery_state="calling")
        db.add(appt); db.flush()
        job = RecoveryJob(org_id=org.id, appointment_id=appt.id, idempotency_key=f"appointment:{appt.id}", provider="twilio", provider_ref="CA999", state="calling")
        db.add(job); db.commit()

    tok = app_client.post("/auth/token", data={"username": "cb2@example.com", "password": "pass123", "org_id": org.id}).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}

    url = "http://testserver/webhooks/twilio"
    sig1 = compute_twilio_signature(auth_token="twilio-test-auth-token", url=url, params={"CallSid": "CA999", "CallStatus": "completed"})
    r1 = app_client.post("/webhooks/twilio", data={"CallSid": "CA999", "CallStatus": "completed"}, headers={"X-Twilio-Signature": sig1})
    assert r1.status_code == 200

    # out-of-order "ringing"
    sig2 = compute_twilio_signature(auth_token="twilio-test-auth-token", url=url, params={"CallSid": "CA999", "CallStatus": "ringing"})
    r2 = app_client.post("/webhooks/twilio", data={"CallSid": "CA999", "CallStatus": "ringing"}, headers={"X-Twilio-Signature": sig2})
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

        # pending -> queued ok
        RecoveryStateMachine.transition(db, appointment=appt, to_state="queued")
        db.commit()

        # queued -> recovered is invalid (must go through calling/messaged)
        try:
            RecoveryStateMachine.transition(db, appointment=appt, to_state="recovered")
            assert False, "expected ValueError"
        except ValueError:
            pass

