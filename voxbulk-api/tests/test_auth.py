from app.core.security import hash_password, verify_password


def _seed_user_org(db):
    from sqlalchemy import select

    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.user import User

    org = Organisation(name="Test Org")
    db.add(org)
    db.flush()

    user = User(email="user@example.com", password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()

    membership = OrganisationMembership(org_id=org.id, user_id=user.id)
    db.add(membership)
    db.commit()

    return user, org


def test_health(app_client):
    r = app_client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_token_and_me(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed_user_org(db)

    r = app_client.post("/auth/token", data={"username": user.email, "password": "pass123", "org_id": org.id})
    assert r.status_code == 200
    token = r.json()["access_token"]

    r2 = app_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert r2.json()["org_id"] == org.id
    assert r2.json()["is_superuser"] is False


def test_register_creates_org_user_and_returns_token(app_client):
    r = app_client.post(
        "/auth/register",
        json={"email": "new@example.com", "password": "pass1234", "organisation_name": "New Org"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["org_id"]
    assert body["user_id"]

    r2 = app_client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert r2.status_code == 200


def test_register_can_join_existing_org_by_org_id(app_client):
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation
    from app.models.membership import OrganisationMembership
    from sqlalchemy import select

    with get_sessionmaker()() as db:
        org = Organisation(name="Existing Org")
        db.add(org)
        db.commit()
        org_id = org.id

    r = app_client.post(
        "/auth/register",
        json={"email": "join@example.com", "password": "pass1234", "organisation_name": "Ignored", "org_id": org_id},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["org_id"] == org_id

    with get_sessionmaker()() as db:
        mem = db.execute(
            select(OrganisationMembership.id).where(
                OrganisationMembership.org_id == org_id,
                OrganisationMembership.user_id == body["user_id"],
            )
        ).scalar_one_or_none()
        assert mem is not None


def test_token_returns_401_if_user_has_no_password_hash(app_client):
    from app.core.database import get_sessionmaker
    from app.models.user import User

    with get_sessionmaker()() as db:
        # Simulate legacy/invalid row (NOT NULL column but empty value).
        u = User(email="nopw@example.com", password_hash="", is_active=True)
        db.add(u)
        db.commit()

    r = app_client.post("/auth/token", data={"username": "nopw@example.com", "password": "anything"})
    assert r.status_code == 401


def test_password_hashing_is_deterministic_scheme():
    hashed = hash_password("pass123")
    assert hashed.startswith("$pbkdf2-sha256$")
    assert verify_password("pass123", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_admin_org_users_lists_invited_registrant(app_client):
    """Invite/register flow: membership is created immediately and admin can list the user."""
    from app.core.database import get_sessionmaker
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.user import User

    with get_sessionmaker()() as db:
        org = Organisation(name="Invite Org")
        db.add(org)
        db.flush()

        admin = User(
            email="admin_invite_list@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
            is_superuser=True,
        )
        db.add(admin)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=admin.id))
        db.commit()
        oid = org.id

    reg = app_client.post(
        "/auth/register",
        json={
            "email": "joiner_list@example.com",
            "password": "pass1234",
            "organisation_name": "ignored",
            "org_id": oid,
        },
    )
    assert reg.status_code == 200
    joiner_id = reg.json()["user_id"]

    su_tok = app_client.post(
        "/auth/token",
        data={"username": "admin_invite_list@example.com", "password": "pass123", "org_id": oid},
    ).json()["access_token"]
    listed = app_client.get(f"/admin/organisations/{oid}/users", headers={"Authorization": f"Bearer {su_tok}"})
    assert listed.status_code == 200
    rows = listed.json()
    assert any(u.get("user_id") == joiner_id and u.get("email") == "joiner_list@example.com" for u in rows)


def test_admin_create_user_and_invite_accept_flow(app_client):
    from app.core.database import get_sessionmaker
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.user import User

    with get_sessionmaker()() as db:
        org = Organisation(name="Admin Create Org")
        db.add(org)
        db.flush()
        admin = User(
            email="admin_create@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
            is_superuser=True,
        )
        db.add(admin)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=admin.id, role="owner"))
        db.commit()
        oid = org.id

    su_tok = app_client.post(
        "/auth/token",
        data={"username": "admin_create@example.com", "password": "pass123", "org_id": oid},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {su_tok}"}

    r_create = app_client.post(
        f"/admin/organisations/{oid}/users",
        headers=headers,
        json={"email": "direct_user@example.com", "password": "pass1234", "role": "dental"},
    )
    assert r_create.status_code == 200
    assert r_create.json()["created_new_user"] is True

    r_inv = app_client.post(
        f"/admin/organisations/{oid}/invites",
        headers=headers,
        json={"email": "invited_user@example.com", "role": "manager"},
    )
    assert r_inv.status_code == 200
    token = r_inv.json()["token"]

    prev = app_client.get(f"/auth/invite-preview?token={token}")
    assert prev.status_code == 200
    assert prev.json()["email"] == "invited_user@example.com"

    acc = app_client.post(
        "/auth/accept-invite",
        json={"token": token, "password": "pass1234"},
    )
    assert acc.status_code == 200
    body = acc.json()
    assert body["org_id"] == oid

    listed = app_client.get(f"/admin/organisations/{oid}/users", headers=headers)
    assert listed.status_code == 200
    emails = {row["email"] for row in listed.json()}
    assert "direct_user@example.com" in emails
    assert "invited_user@example.com" in emails


def test_admin_org_users_lists_self_serve_user_before_and_after_approve(app_client):
    """Self-serve: membership exists while pending; approve only activates login — admin list still sees the row."""
    from app.core.database import get_sessionmaker
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.user import User

    with get_sessionmaker()() as db:
        anchor = Organisation(name="Admin Anchor Org")
        db.add(anchor)
        db.flush()
        admin = User(
            email="admin_ss_list@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
            is_superuser=True,
        )
        db.add(admin)
        db.flush()
        db.add(OrganisationMembership(org_id=anchor.id, user_id=admin.id))
        db.commit()
        anchor_id = anchor.id

    ss = app_client.post(
        "/auth/self-serve",
        json={
            "email": "selfserve_member@example.com",
            "password": "pass1234",
            "organisation_name": "Self Serve Clinic",
            "plan_code": "starter",
            "payment_method": "bank_transfer",
        },
    )
    assert ss.status_code == 200
    body = ss.json()
    request_id = body["request_id"]
    new_org_id = body["org_id"]
    new_user_id = body["user_id"]

    su_tok = app_client.post(
        "/auth/token",
        data={"username": "admin_ss_list@example.com", "password": "pass123", "org_id": anchor_id},
    ).json()["access_token"]

    listed_pending = app_client.get(
        f"/admin/organisations/{new_org_id}/users",
        headers={"Authorization": f"Bearer {su_tok}"},
    )
    assert listed_pending.status_code == 200
    assert any(u.get("user_id") == new_user_id for u in listed_pending.json())

    approved = app_client.post(
        f"/admin/onboarding/requests/{request_id}/approve",
        headers={"Authorization": f"Bearer {su_tok}"},
        json={},
    )
    assert approved.status_code == 200

    listed_after = app_client.get(
        f"/admin/organisations/{new_org_id}/users",
        headers={"Authorization": f"Bearer {su_tok}"},
    )
    assert listed_after.status_code == 200
    assert any(
        u.get("user_id") == new_user_id and u.get("email") == "selfserve_member@example.com"
        for u in listed_after.json()
    )

