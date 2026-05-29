"""Team invites, opt-out list, audit log, and org logo upload."""

from __future__ import annotations

import io

from app.core.security import hash_password


def _seed_owner(db):
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.user import User

    org = Organisation(name="Settings Org")
    db.add(org)
    db.flush()
    user = User(email="owner@settings.test", password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    db.commit()
    return user, org


def _token(client, user, org_id):
    r = client.post("/auth/token", data={"username": user.email, "password": "pass123", "org_id": org_id})
    assert r.status_code == 200
    return r.json()["access_token"]


def test_team_invite_opt_out_audit_and_logo(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed_owner(db)

    headers = {"Authorization": f"Bearer {_token(app_client, user, org.id)}"}

    inv = app_client.post(
        "/organisations/me/team/invites",
        headers=headers,
        json={"email": "accountant@settings.test", "role": "accountant", "send_email": False},
    )
    assert inv.status_code == 200, inv.text
    body = inv.json()
    assert body["email"] == "accountant@settings.test"
    assert "signup_url" in body

    members = app_client.get("/organisations/me/team/members", headers=headers)
    assert members.status_code == 200
    assert len(members.json()) >= 1

    pending = app_client.get("/organisations/me/team/invites", headers=headers)
    assert pending.status_code == 200
    assert len(pending.json()) == 1

    opt = app_client.post(
        "/organisations/me/opt-outs",
        headers=headers,
        json={"phone": "+447700900123", "name": "Test User", "reason": "Requested removal"},
    )
    assert opt.status_code == 200, opt.text
    opt_id = opt.json()["id"]

    listed = app_client.get("/organisations/me/opt-outs", headers=headers)
    assert listed.status_code == 200
    assert any(row["id"] == opt_id for row in listed.json())

    png = io.BytesIO(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    logo_up = app_client.post(
        "/organisations/me/logo",
        headers=headers,
        files={"file": ("logo.png", png.getvalue(), "image/png")},
    )
    assert logo_up.status_code == 200, logo_up.text
    assert logo_up.json()["logo_url"] == "/organisations/me/logo/file"

    me = app_client.get("/organisations/me", headers=headers)
    assert me.status_code == 200
    assert me.json().get("logo_url") == "/organisations/me/logo/file"

    logo_get = app_client.get("/organisations/me/logo/file", headers=headers)
    assert logo_get.status_code == 200
    assert logo_get.headers["content-type"].startswith("image/")

    audit = app_client.get("/organisations/me/audit-log", headers=headers)
    assert audit.status_code == 200
    actions = {row["action"] for row in audit.json()}
    assert "team.invite_sent" in actions
    assert "opt_out.added" in actions
    assert "profile.logo_updated" in actions

    rm_opt = app_client.delete(f"/organisations/me/opt-outs/{opt_id}", headers=headers)
    assert rm_opt.status_code == 200

    del_logo = app_client.delete("/organisations/me/logo", headers=headers)
    assert del_logo.status_code == 200


def test_scheduling_status_includes_interview_ready(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed_owner(db)

    headers = {"Authorization": f"Bearer {_token(app_client, user, org.id)}"}
    st = app_client.get("/service-orders/scheduling/status", headers=headers)
    assert st.status_code == 200
    data = st.json()
    assert data.get("interview_booking_ready") is True
    assert "calendly_connected" in data
    assert "cronofy_connected" in data
