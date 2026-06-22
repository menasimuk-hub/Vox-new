from __future__ import annotations

from app.core.security import hash_password


def _seed_superuser_org(db, *, email: str = "services-admin@example.com"):
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.user import User

    org = Organisation(name="Services Test Org")
    db.add(org)
    db.flush()
    user = User(email=email, password_hash=hash_password("pass123"), is_active=True, is_superuser=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    db.commit()
    return user, org


def _token(app_client, user, org):
    res = app_client.post("/auth/token", data={"username": user.email, "password": "pass123", "org_id": org.id})
    assert res.status_code == 200
    return res.json()["access_token"]


from app.services.org_enabled_services import apply_admin_org_service_grants, effective_services


def test_apply_admin_org_service_grants_revokes_modules():
    enabled = {
        "interview": True,
        "survey": True,
        "customer_feedback": True,
        "appointments": False,
        "recovery": True,
        "follow_up": True,
        "campaigns": True,
    }
    grants = {
        "interview": True,
        "survey": True,
        "customer_feedback": False,
        "appointments": False,
        "recovery": False,
        "follow_up": False,
        "campaigns": False,
    }
    allowed, next_enabled = apply_admin_org_service_grants(enabled, grants)
    assert allowed["campaigns"] is False
    assert allowed["recovery"] is False
    assert next_enabled["campaigns"] is False
    assert next_enabled["recovery"] is False
    assert effective_services(allowed, next_enabled)["interview"] is True


def test_admin_get_allowed_services_includes_breakdown(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed_superuser_org(db)
    headers = {"Authorization": f"Bearer {_token(app_client, user, org)}"}

    r = app_client.get(f"/admin/organisations/{org.id}/allowed-services", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert "service_breakdown" in body
    assert "platform_default_allowed" in body
    assert len(body["service_breakdown"]) == 7
    interview = next(row for row in body["service_breakdown"] if row["key"] == "interview")
    assert interview["allowed"] is True
    assert interview["label"] == "Interviews"
    assert interview["customer_status"] in {"Not granted", "Available in Settings", "Visible in app"}


def test_admin_patch_customer_feedback_allowed_without_auto_enable(app_client):
    from app.core.database import get_sessionmaker
    from app.services.org_enabled_services import org_service_maps, serialize_allowed_services, serialize_enabled_services

    with get_sessionmaker()() as db:
        user, org = _seed_superuser_org(db, email="services-grant@example.com")
        allowed, enabled, _ = org_service_maps(org, db)
        enabled = dict(enabled)
        enabled["customer_feedback"] = False
        org.allowed_services_json = serialize_allowed_services(allowed)
        org.enabled_services_json = serialize_enabled_services(enabled)
        db.add(org)
        db.commit()

    headers = {"Authorization": f"Bearer {_token(app_client, user, org)}"}
    patch = app_client.patch(
        f"/admin/organisations/{org.id}/allowed-services",
        json={"customer_feedback": True},
        headers=headers,
    )
    assert patch.status_code == 200
    body = patch.json()
    assert body["allowed_services"]["customer_feedback"] is True
    assert body["enabled_services"]["customer_feedback"] is False
    assert "service_breakdown" in body
    feedback = next(row for row in body["service_breakdown"] if row["key"] == "customer_feedback")
    assert feedback["customer_status"] == "Available in Settings"
