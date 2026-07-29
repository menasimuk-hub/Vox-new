"""Phase 7: tenant order lookup, recovery task org bind, partner owner fail-hard."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.dentally_appointment import DentallyAppointment
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.patient import Patient
from app.models.recovery_job import RecoveryJob
from app.models.user import User
from app.services.partner_service import PartnerService
from app.services.platform_catalog_service import ServiceOrderService


def test_get_order_requires_org_id():
    with get_sessionmaker()() as db:
        with pytest.raises(ValueError, match="org_id is required"):
            ServiceOrderService.get_order(db, "missing-order")


def test_get_order_unscoped_allowed_for_admin_tools():
    with get_sessionmaker()() as db:
        assert ServiceOrderService.get_order(db, "missing-order", unscoped=True) is None


def test_partner_owner_fails_when_org_has_no_members():
    with get_sessionmaker()() as db:
        org = Organisation(name="Empty Partner Org")
        db.add(org)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            PartnerService._org_owner_user_id(db, org.id)
        assert exc.value.status_code == 400
        assert "no members" in str(exc.value.detail).lower()


def test_recovery_task_status_is_org_bound(app_client):
    with get_sessionmaker()() as db:
        org_a = Organisation(name="Recovery Org A")
        org_b = Organisation(name="Recovery Org B")
        db.add_all([org_a, org_b])
        db.flush()
        user_b = User(
            email="recovery-b@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
        )
        db.add(user_b)
        db.flush()
        db.add(OrganisationMembership(org_id=org_b.id, user_id=user_b.id, role="owner"))
        patient = Patient(org_id=org_a.id, first_name="Pat", last_name="A")
        db.add(patient)
        db.flush()
        appt = DentallyAppointment(
            org_id=org_a.id,
            patient_id=patient.id,
            scheduled_start=datetime.now(timezone.utc),
            status="scheduled",
        )
        db.add(appt)
        db.flush()
        job = RecoveryJob(
            org_id=org_a.id,
            dentally_appointment_id=appt.id,
            idempotency_key="idem-org-bound",
            celery_task_id="celery-task-org-a",
            state="queued",
        )
        db.add(job)
        db.commit()
        email_b = user_b.email
        org_b_id = org_b.id

    tok = app_client.post(
        "/auth/token",
        data={"username": email_b, "password": "pass123", "org_id": org_b_id},
    ).json()["access_token"]
    r = app_client.get(
        "/calls/recovery/tasks/celery-task-org-a",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 404
