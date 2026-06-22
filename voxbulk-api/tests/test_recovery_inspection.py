from app.core.security import hash_password


def _seed(db):
    from datetime import datetime, timezone

    from app.models.dentally_appointment import DentallyAppointment
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.recovery_job import RecoveryJob
    from app.models.user import User

    org = Organisation(name="Inspect Org")
    db.add(org)
    db.flush()
    user = User(email="inspect@example.com", password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
    appt = Appointment(org_id=org.id, scheduled_start=datetime.now(timezone.utc), status="scheduled")
    db.add(appt)
    db.flush()
    job = RecoveryJob(org_id=org.id, appointment_id=appt.id, idempotency_key=f"appointment:{appt.id}", state="queued")
    db.add(job)
    db.commit()
    return user, org, appt, job


def test_recovery_job_list_and_get(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org, appt, job = _seed(db)

    tok = app_client.post("/auth/token", data={"username": user.email, "password": "pass123", "org_id": org.id}).json()[
        "access_token"
    ]
    headers = {"Authorization": f"Bearer {tok}"}

    r = app_client.get("/calls/recovery/jobs", headers=headers)
    assert r.status_code == 200
    assert any(x["job_id"] == job.id for x in r.json())

    r2 = app_client.get(f"/calls/recovery/jobs/{job.id}", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["job_id"] == job.id

    r3 = app_client.get(f"/calls/recovery/appointments/{appt.id}/jobs", headers=headers)
    assert r3.status_code == 200
    assert len(r3.json()) >= 1

