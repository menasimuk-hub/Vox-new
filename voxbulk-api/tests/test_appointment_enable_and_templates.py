"""Tests for appointments enable patch and WA template catalog."""

from __future__ import annotations

import json

from app.core.security import hash_password
from app.services.appointment_whatsapp_template_service import AppointmentWhatsappTemplateService
from app.services.org_enabled_services import (
    merge_admin_allowed_services,
    org_service_maps,
    parse_enabled_services,
    serialize_allowed_services,
    serialize_enabled_services,
)


def _seed_org_user(db, *, email: str = "appt-enable@example.com"):
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.user import User

    org = Organisation(name="Appt Enable Org")
    db.add(org)
    db.flush()
    user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    db.commit()
    return user, org


def _headers(app_client, user, org):
    res = app_client.post("/auth/token", data={"username": user.email, "password": "pass123", "org_id": org.id})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_enabled_services_patch_includes_appointments(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed_org_user(db)
        allowed, enabled, _ = org_service_maps(org, db)
        allowed, enabled = merge_admin_allowed_services(allowed, enabled, {"appointments": True})
        org.allowed_services_json = serialize_allowed_services(allowed)
        org.enabled_services_json = serialize_enabled_services(enabled)
        db.add(org)
        db.commit()

    headers = _headers(app_client, user, org)
    res = app_client.patch(
        "/organisations/me/enabled-services",
        headers=headers,
        json={"appointments": True},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    enabled_out = body.get("enabled_services") or {}
    assert enabled_out.get("appointments") is True

    me = app_client.get("/organisations/me", headers=headers)
    assert me.json()["enabled_services"]["appointments"] is True


def test_appointment_wa_templates_seeded():
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        rows = AppointmentWhatsappTemplateService.list_customer_templates(db)
    names = {r["name"] for r in rows}
    assert "appt_confirm_v1" in names
    assert "appt_confirm_v2" in names
    assert "appt_reminder_v1" in names
    assert "appt_reminder_v2" in names
    assert len(rows) == 4


def test_parse_enabled_services_has_appointments_key():
    parsed = parse_enabled_services(json.dumps({"interview": True, "appointments": True}))
    assert parsed.get("appointments") is True
