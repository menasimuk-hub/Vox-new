from app.core.security import hash_password


def _seed_org_user(db, email: str, org_name: str):
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.user import User

    org = Organisation(name=org_name)
    db.add(org)
    db.flush()

    user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()

    db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
    db.commit()
    return user, org


def _token(client, email: str, org_id: str) -> str:
    r = client.post("/auth/token", data={"username": email, "password": "pass123", "org_id": org_id})
    assert r.status_code == 200
    return r.json()["access_token"]


def test_tenant_isolation_patient_and_appointment(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        u1, o1 = _seed_org_user(db, "iso1@example.com", "Org1")
        u2, o2 = _seed_org_user(db, "iso2@example.com", "Org2")

    t1 = _token(app_client, u1.email, o1.id)
    t2 = _token(app_client, u2.email, o2.id)
    h1 = {"Authorization": f"Bearer {t1}"}
    h2 = {"Authorization": f"Bearer {t2}"}

    # Org1 creates branch + patient
    b1 = app_client.post("/branches", json={"name": "B1"}, headers=h1).json()
    p1 = app_client.post(
        "/patients",
        json={"first_name": "A", "last_name": "B", "branch_id": b1["id"]},
        headers=h1,
    ).json()

    # Org2 should not see Org1 patient
    r = app_client.get(f"/patients/{p1['id']}", headers=h2)
    assert r.status_code == 404

    # Org1 creates appointment for its patient
    a1 = app_client.post(
        "/dentally/appointments",
        json={"scheduled_start": "2026-05-05T10:00:00Z", "patient_id": p1["id"]},
        headers=h1,
    ).json()

    # Org2 cannot access Org1 appointment
    r2 = app_client.get(f"/dentally/appointments/{a1['id']}", headers=h2)
    assert r2.status_code == 404

