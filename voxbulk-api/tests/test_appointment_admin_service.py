"""Tests for Appointment Manager admin operations overview."""

from __future__ import annotations

from app.core.security import hash_password
from app.services.appointment_admin_service import list_organisations
from app.services.org_enabled_services import (
    merge_admin_allowed_services,
    org_service_maps,
    serialize_allowed_services,
    serialize_enabled_services,
)


def _seed_org_with_appointments(db, *, name: str = "Clinic Alpha"):
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.user import User

    org = Organisation(name=name, contact_email="clinic@example.com")
    db.add(org)
    db.flush()
    user = User(email=f"{name.lower().replace(' ', '-')}@example.com", password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    allowed, enabled, _ = org_service_maps(org, db)
    allowed, enabled = merge_admin_allowed_services(allowed, enabled, {"appointments": True})
    enabled["appointments"] = True
    org.allowed_services_json = serialize_allowed_services(allowed)
    org.enabled_services_json = serialize_enabled_services(enabled)
    db.commit()
    return org


def test_list_organisations_uses_org_name_not_display_name():
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        org = _seed_org_with_appointments(db, name="Sunrise Dental")
        rows = list_organisations(db)
    match = next((r for r in rows if r["org_id"] == org.id), None)
    assert match is not None
    assert match["org_name"] == "Sunrise Dental"
    assert match["contact_email"] == "clinic@example.com"
