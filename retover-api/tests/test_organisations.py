from app.core.security import hash_password


def _seed_user_org(db):
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.user import User

    org = Organisation(name="Org A")
    db.add(org)
    db.flush()

    user = User(email="user2@example.com", password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()

    db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
    db.commit()
    return user, org


def test_organisations_me(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed_user_org(db)

    r = app_client.post("/auth/token", data={"username": user.email, "password": "pass123", "org_id": org.id})
    token = r.json()["access_token"]

    r2 = app_client.get("/organisations/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert r2.json()["id"] == org.id


def test_billing_plans_and_subscription_empty(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed_user_org(db)

    r = app_client.post("/auth/token", data={"username": user.email, "password": "pass123", "org_id": org.id})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    plans = app_client.get("/billing/plans")
    assert plans.status_code == 200
    pj = plans.json()
    assert isinstance(pj, list)
    assert len(pj) >= 1

    sub = app_client.get("/billing/subscription", headers=headers)
    assert sub.status_code == 200
    body = sub.json()
    assert body.get("subscription") is None
    assert body.get("plan") is None

