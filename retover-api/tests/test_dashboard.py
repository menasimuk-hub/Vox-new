from app.core.security import hash_password


def _seed(db):
    from datetime import datetime, timezone

    from app.models.appointment import Appointment
    from app.models.call_log import CallLog
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.patient import Patient
    from app.models.user import User
    from app.models.whatsapp_log import WhatsAppLog

    org = Organisation(name="Dash Org")
    db.add(org)
    db.flush()
    user = User(email="dash@example.com", password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id))

    p = Patient(org_id=org.id, first_name="A", last_name="B")
    db.add(p)
    db.flush()

    a1 = Appointment(org_id=org.id, patient_id=p.id, scheduled_start=datetime.now(timezone.utc), status="scheduled")
    a2 = Appointment(org_id=org.id, patient_id=p.id, scheduled_start=datetime.now(timezone.utc), status="cancelled")
    db.add_all([a1, a2])
    db.flush()

    db.add(CallLog(org_id=org.id, appointment_id=a1.id, status="queued"))
    db.add(WhatsAppLog(org_id=org.id, appointment_id=a1.id, status="queued"))
    db.commit()
    return user, org


def test_dashboard_metrics(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed(db)

    tok = app_client.post("/auth/token", data={"username": user.email, "password": "pass123", "org_id": org.id}).json()[
        "access_token"
    ]
    r = app_client.get("/dashboard/metrics", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    payload = r.json()
    assert payload["total_patients"] == 1
    assert payload["total_appointments"] == 2
    assert payload["total_call_logs"] == 1
    assert payload["total_whatsapp_logs"] == 1
    assert payload["appointment_status_counts"]["scheduled"] == 1
    assert payload["appointment_status_counts"]["cancelled"] == 1

