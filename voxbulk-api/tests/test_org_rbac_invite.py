"""Org RBAC, multi-org login, team invite email."""

from __future__ import annotations

from sqlalchemy import select

from app.core.security import hash_password
from app.data.system_email_defaults import SYSTEM_EMAIL_DEFAULTS
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.email_template_service import EMAIL_TEMPLATE_KEYS
from app.services.org_rbac import OrgRbacService, effective_role


def test_team_invite_and_org_switch_flow(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        org = Organisation(name="Acme Dental")
        db.add(org)
        db.flush()
        owner = User(email="owner_rbac@example.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(owner)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=owner.id, role="owner"))
        db.commit()
        org_id = org.id

    owner_tok = app_client.post(
        "/auth/token",
        data={"username": "owner_rbac@example.com", "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {owner_tok}"}

    inv = app_client.post(
        "/organisations/me/team/invites",
        headers=headers,
        json={"email": "accountant_rbac@example.com", "role": "accountant"},
    )
    assert inv.status_code == 200
    token = inv.json()["signup_url"].split("invite_token=")[-1]

    acc = app_client.post("/auth/accept-invite", json={"token": token, "password": "pass1234"})
    assert acc.status_code == 200
    assert acc.json()["org_id"] == org_id

    with get_sessionmaker()() as db:
        org2 = Organisation(name="Side Practice")
        db.add(org2)
        db.flush()
        owner = db.execute(select(User).where(User.email == "owner_rbac@example.com")).scalar_one()
        db.add(OrganisationMembership(org_id=org2.id, user_id=owner.id, role="owner"))
        db.commit()

    pick = app_client.post("/auth/token", data={"username": "owner_rbac@example.com", "password": "pass123"})
    assert pick.status_code == 200
    body = pick.json()
    assert body.get("org_selection_required") is True
    assert len(body.get("organisations") or []) == 2

    login_org = app_client.post(
        "/auth/token",
        data={"username": "owner_rbac@example.com", "password": "pass123", "org_id": org_id},
    )
    assert login_org.status_code == 200
    acct_tok = login_org.json()["access_token"]

    listed = app_client.get("/auth/my-organisations", headers={"Authorization": f"Bearer {acct_tok}"})
    assert listed.status_code == 200
    assert listed.json()["active_org_id"] == org_id


def test_member_blocked_from_billing(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        org = Organisation(name="Campaign Only")
        db.add(org)
        db.flush()
        user = User(email="member_rbac@example.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="member"))
        db.commit()
        org_id = org.id

    tok = app_client.post(
        "/auth/token",
        data={"username": "member_rbac@example.com", "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}

    blocked = app_client.get("/billing/wallet", headers=headers)
    assert blocked.status_code == 403


def test_cannot_remove_only_owner(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        org = Organisation(name="Solo Owner")
        db.add(org)
        db.flush()
        owner = User(email="solo_owner@example.com", password_hash=hash_password("pass123"), is_active=True)
        mgr = User(email="mgr_remove@example.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(owner)
        db.add(mgr)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=owner.id, role="owner"))
        db.add(OrganisationMembership(org_id=org.id, user_id=mgr.id, role="manager"))
        db.commit()
        org_id = org.id
        owner_id = owner.id

    mgr_tok = app_client.post(
        "/auth/token",
        data={"username": "mgr_remove@example.com", "password": "pass123", "org_id": org_id},
    ).json()["access_token"]

    resp = app_client.delete(
        f"/organisations/me/team/members/{owner_id}",
        headers={"Authorization": f"Bearer {mgr_tok}"},
    )
    assert resp.status_code == 400


def test_team_invite_template_registered():
    assert "team_invite" in EMAIL_TEMPLATE_KEYS
    assert "weekly_digest" in EMAIL_TEMPLATE_KEYS
    assert "{{organisation_name}}" in SYSTEM_EMAIL_DEFAULTS["team_invite"]["body"]
    assert "{{signup_url}}" in SYSTEM_EMAIL_DEFAULTS["team_invite"]["body"]


def test_null_role_membership_treated_as_owner(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        org = Organisation(name="Legacy Owner Co")
        db.add(org)
        db.flush()
        user = User(email="legacy_owner@example.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role=None))
        db.commit()
        org_id = org.id

    tok = app_client.post(
        "/auth/token",
        data={"username": "legacy_owner@example.com", "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}

    me = app_client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["role"] == "owner"

    wallet = app_client.get("/billing/wallet", headers=headers)
    assert wallet.status_code == 200


def test_register_sets_owner_role(app_client):
    from app.core.database import get_sessionmaker

    resp = app_client.post(
        "/auth/register",
        json={
            "email": "new_owner_reg@example.com",
            "password": "pass12345",
            "organisation_name": "New Owner Org",
        },
    )
    assert resp.status_code == 200
    user_id = resp.json()["user_id"]
    org_id = resp.json()["org_id"]

    with get_sessionmaker()() as db:
        mem = db.execute(
            select(OrganisationMembership).where(
                OrganisationMembership.user_id == user_id,
                OrganisationMembership.org_id == org_id,
            )
        ).scalar_one()
        assert mem.role == "owner"
        assert effective_role(mem.role) == "owner"


def test_new_invite_user_gets_personal_and_inviter_org(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        org = Organisation(name="Inviter Co")
        db.add(org)
        db.flush()
        owner = User(email="inviter_owner@example.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(owner)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=owner.id, role="owner"))
        db.commit()
        inviter_org_id = org.id

    owner_tok = app_client.post(
        "/auth/token",
        data={"username": "inviter_owner@example.com", "password": "pass123", "org_id": inviter_org_id},
    ).json()["access_token"]
    inv = app_client.post(
        "/organisations/me/team/invites",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"email": "new_invitee@example.com", "role": "accountant"},
    )
    assert inv.status_code == 200
    token = inv.json()["signup_url"].split("invite_token=")[-1]

    acc = app_client.post("/auth/accept-invite", json={"token": token, "password": "pass1234"})
    assert acc.status_code == 200
    assert acc.json()["org_id"] == inviter_org_id
    user_id = acc.json()["user_id"]

    with get_sessionmaker()() as db:
        mems = list(
            db.execute(select(OrganisationMembership).where(OrganisationMembership.user_id == user_id)).scalars()
        )
        assert len(mems) == 2
        roles = {str(m.org_id): m.role for m in mems}
        assert roles[inviter_org_id] == "accountant"
        owner_orgs = [m.org_id for m in mems if effective_role(m.role) == "owner"]
        assert len(owner_orgs) == 1
        assert owner_orgs[0] != inviter_org_id


def test_pending_invites_and_accept_session(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        inviter = Organisation(name="Pending Inviter")
        personal = Organisation(name="Personal Org")
        db.add(inviter)
        db.add(personal)
        db.flush()
        user = User(email="pending_user@example.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=personal.id, user_id=user.id, role="owner"))
        db.commit()
        personal_org_id = personal.id
        inviter_org_id = inviter.id

    owner = User(email="pi_owner@example.com", password_hash=hash_password("pass123"), is_active=True)
    with get_sessionmaker()() as db:
        db.add(owner)
        db.flush()
        db.add(OrganisationMembership(org_id=inviter_org_id, user_id=owner.id, role="owner"))
        db.commit()

    owner_tok = app_client.post(
        "/auth/token",
        data={"username": "pi_owner@example.com", "password": "pass123", "org_id": inviter_org_id},
    ).json()["access_token"]

    user_tok = app_client.post(
        "/auth/token",
        data={"username": "pending_user@example.com", "password": "pass123", "org_id": personal_org_id},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {user_tok}"}

    inv = app_client.post(
        "/organisations/me/team/invites",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"email": "pending_user@example.com", "role": "accountant"},
    )
    assert inv.status_code == 200
    invite_token = inv.json()["signup_url"].split("invite_token=")[-1]

    pending = app_client.get("/auth/pending-invites", headers=headers)
    assert pending.status_code == 200
    assert len(pending.json()["invites"]) == 1

    accepted = app_client.post("/auth/accept-invite-session", headers=headers, json={"token": invite_token})
    assert accepted.status_code == 200
    assert accepted.json()["org_id"] == inviter_org_id

    acct_tok = accepted.json()["access_token"]
    wallet = app_client.get("/billing/wallet", headers={"Authorization": f"Bearer {acct_tok}"})
    assert wallet.status_code == 200


def test_password_login_attaches_pending_invite(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        inviter = Organisation(name="Pwd Inviter")
        personal = Organisation(name="Pwd Personal")
        db.add(inviter)
        db.add(personal)
        db.flush()
        user = User(email="pwd_invite@example.com", password_hash=hash_password("pass123"), is_active=True)
        owner = User(email="pwd_inv_owner@example.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.add(owner)
        db.flush()
        db.add(OrganisationMembership(org_id=personal.id, user_id=user.id, role="owner"))
        db.add(OrganisationMembership(org_id=inviter.id, user_id=owner.id, role="owner"))
        db.commit()
        personal_org_id = personal.id
        inviter_org_id = inviter.id

    owner_tok = app_client.post(
        "/auth/token",
        data={"username": "pwd_inv_owner@example.com", "password": "pass123", "org_id": inviter_org_id},
    ).json()["access_token"]
    inv = app_client.post(
        "/organisations/me/team/invites",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"email": "pwd_invite@example.com", "role": "accountant"},
    )
    assert inv.status_code == 200

    login = app_client.post(
        "/auth/token",
        data={"username": "pwd_invite@example.com", "password": "pass123"},
    )
    assert login.status_code == 200
    body = login.json()
    assert body.get("org_selection_required") is True
    org_ids = {o["org_id"] for o in body.get("organisations") or []}
    assert personal_org_id in org_ids
    assert inviter_org_id in org_ids

    picked = app_client.post(
        "/auth/token",
        data={
            "username": "pwd_invite@example.com",
            "password": "pass123",
            "org_id": inviter_org_id,
        },
    )
    assert picked.status_code == 200
    tok = picked.json()["access_token"]
    wallet = app_client.get("/billing/wallet", headers={"Authorization": f"Bearer {tok}"})
    assert wallet.status_code == 200


def test_org_rbac_service_roles():
    from app.core.database import get_sessionmaker

    assert effective_role("receptionist") == "member"
    assert effective_role(None) == "owner"

    with get_sessionmaker()() as db:
        org = Organisation(name="RBAC Unit")
        db.add(org)
        db.flush()
        user = User(email="rbac_unit@example.com", password_hash=hash_password("x"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="accountant"))
        db.commit()
        OrgRbacService.assert_can_access_billing(db, org_id=org.id, user_id=user.id)
        try:
            OrgRbacService.assert_can_launch_campaigns(db, org_id=org.id, user_id=user.id)
            raise AssertionError("accountant should not launch campaigns")
        except PermissionError:
            pass


def test_team_invite_rejects_receptionist_role(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        org = Organisation(name="No Receptionist Co")
        db.add(org)
        db.flush()
        owner = User(email="no_recep_owner@example.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(owner)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=owner.id, role="owner"))
        db.commit()
        org_id = org.id

    owner_tok = app_client.post(
        "/auth/token",
        data={"username": "no_recep_owner@example.com", "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {owner_tok}"}

    inv = app_client.post(
        "/organisations/me/team/invites",
        headers=headers,
        json={"email": "recep_test@example.com", "role": "receptionist"},
    )
    assert inv.status_code == 400
