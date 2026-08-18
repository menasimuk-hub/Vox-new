"""Organisation DSAR / portability ZIP for owners and managers."""

from __future__ import annotations

import io
import json
import zipfile

from app.core.security import hash_password


def _seed(db, *, email: str, role: str, org_name: str = "Export Org"):
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.user import User

    org = Organisation(name=org_name, contact_email="ops@export.test")
    db.add(org)
    db.flush()
    user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role=role))
    db.commit()
    return user, org


def _token(client, user, org_id: str) -> str:
    r = client.post("/auth/token", data={"username": user.email, "password": "pass123", "org_id": org_id})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_owner_can_download_data_export_zip(app_client):
    from app.core.database import get_sessionmaker
    from app.models.service_order import ServiceOrder, ServiceOrderRecipient

    with get_sessionmaker()() as db:
        user, org = _seed(db, email="owner-export@example.com", role="owner")
        order = ServiceOrder(
            org_id=org.id,
            user_id=user.id,
            service_code="survey",
            title="Clinic NPS",
            status="completed",
        )
        db.add(order)
        db.flush()
        db.add(
            ServiceOrderRecipient(
                order_id=order.id,
                name="Pat Example",
                phone="+447700900999",
                email="pat@example.com",
                status="completed",
                result_json='{"score": 9, "secret": "should-not-appear"}',
            )
        )
        db.commit()
        org_id = org.id

    headers = {"Authorization": f"Bearer {_token(app_client, user, org_id)}"}
    res = app_client.get("/organisations/me/data-export", headers=headers)
    assert res.status_code == 200, res.text
    assert res.headers.get("content-type", "").startswith("application/zip")
    assert "attachment" in (res.headers.get("content-disposition") or "")

    with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
        names = set(zf.namelist())
        assert "README.txt" in names
        assert "organisation.json" in names
        assert "campaigns.json" in names
        org_payload = json.loads(zf.read("organisation.json"))
        assert org_payload["id"] == org_id
        assert org_payload["name"] == "Export Org"
        campaigns = json.loads(zf.read("campaigns.json"))
        assert campaigns["campaigns"][0]["title"] == "Clinic NPS"
        recipient = campaigns["campaigns"][0]["recipients"][0]
        assert recipient["name"] == "Pat Example"
        assert recipient["has_result_payload"] is True
        raw = zf.read("campaigns.json").decode("utf-8")
        assert "should-not-appear" not in raw
        assert "password_hash" not in zf.read("memberships.json").decode("utf-8")


def test_member_cannot_download_data_export(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed(db, email="member-export@example.com", role="member")

    headers = {"Authorization": f"Bearer {_token(app_client, user, org.id)}"}
    res = app_client.get("/organisations/me/data-export", headers=headers)
    assert res.status_code == 403


def test_manager_can_download_data_export(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed(db, email="manager-export@example.com", role="manager", org_name="Mgr Org")

    headers = {"Authorization": f"Bearer {_token(app_client, user, org.id)}"}
    res = app_client.get("/organisations/me/data-export", headers=headers)
    assert res.status_code == 200, res.text
    with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
        assert "consent.json" in zf.namelist()
