"""Partner marketplace API: auth, health, screenings."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.partner_service import PartnerService


@pytest.fixture()
def client(app_client: TestClient):
    return app_client


def _seed_partner_ready(*, environment: str = "sandbox"):
    with get_sessionmaker()() as db:
        org = Organisation(name=f"Partner Org {uuid.uuid4().hex[:6]}")
        db.add(org)
        db.flush()
        user = User(
            email=f"partner-{uuid.uuid4().hex[:8]}@test.com",
            password_hash=hash_password("pass123"),
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
        db.commit()
        org_id = org.id

        PartnerService.ensure_providers(db)
        PartnerService.admin_update_provider(
            db,
            "zoho",
            {
                "enabled": True,
                "mode": environment,
                "mapped_org_id": org_id,
                "result_webhook_url": "https://example.com/hooks/voxbulk",
            },
        )
        key_payload = PartnerService.admin_generate_key(db, "zoho", environment=environment)
        return {
            "org_id": org_id,
            "api_key": key_payload["api_key"],
            "partner_name": "zoho",
        }


def test_partner_health_public(client: TestClient):
    res = client.get("/partner/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "partner-api"


def test_partner_screening_requires_auth(client: TestClient):
    res = client.post(
        "/partner/v1/screenings",
        json={
            "partner_reference_id": "ref-1",
            "job_title": "Nurse",
            "screening_questions": ["Tell me about yourself"],
            "candidate_name": "Ada",
            "candidate_phone": "+447700900111",
            "preferred_language": "en",
        },
    )
    assert res.status_code == 401


def test_partner_screening_rejects_bad_key(client: TestClient):
    _seed_partner_ready()
    res = client.post(
        "/partner/v1/screenings",
        headers={"X-API-Key": "vb_zoho_sandbox_invalid", "X-Partner-Name": "zoho"},
        json={
            "partner_reference_id": "ref-bad",
            "job_title": "Nurse",
            "screening_questions": [],
            "candidate_name": "Ada",
            "candidate_phone": "+447700900111",
            "preferred_language": "en",
        },
    )
    assert res.status_code == 401


def test_partner_create_screening_ok(client: TestClient):
    seeded = _seed_partner_ready()
    res = client.post(
        "/partner/v1/screenings",
        headers={"X-API-Key": seeded["api_key"], "X-Partner-Name": "zoho"},
        json={
            "partner_reference_id": "zoho-cand-001",
            "job_title": "Dental Nurse",
            "screening_questions": ["Describe patient care experience", "Are you GDC registered?"],
            "candidate_name": "Sara Ali",
            "candidate_phone": "+447700900222",
            "preferred_language": "en",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] in {"accepted", "invited"}
    assert body["partner_reference_id"] == "zoho-cand-001"
    assert body["screening_id"]
    assert body["screening_link"]
    assert body["estimated_completion_minutes"] >= 1


def test_partner_create_screening_ar(client: TestClient):
    seeded = _seed_partner_ready()
    res = client.post(
        "/partner/v1/screenings",
        headers={"X-API-Key": seeded["api_key"], "X-Partner-Name": "zoho"},
        json={
            "partner_reference_id": "zoho-cand-ar-1",
            "job_title": "موظف استقبال",
            "screening_questions": ["صف خبرتك"],
            "candidate_name": "أحمد",
            "candidate_phone": "+971500000001",
            "preferred_language": "ar",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] in {"accepted", "invited"}


def test_partner_results_log(client: TestClient):
    seeded = _seed_partner_ready()
    create = client.post(
        "/partner/v1/screenings",
        headers={"X-API-Key": seeded["api_key"], "X-Partner-Name": "zoho"},
        json={
            "partner_reference_id": "zoho-cand-res",
            "job_title": "Receptionist",
            "screening_questions": ["Why this role?"],
            "candidate_name": "Pat",
            "candidate_phone": "+447700900333",
            "preferred_language": "en",
        },
    )
    assert create.status_code == 200
    screening_id = create.json()["screening_id"]
    res = client.post(
        "/partner/v1/results",
        headers={"X-API-Key": seeded["api_key"], "X-Partner-Name": "zoho"},
        json={
            "partner_reference_id": "zoho-cand-res",
            "screening_id": screening_id,
            "candidate_score": 82,
            "status": "passed",
            "call_duration_minutes": 12,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["received"] is True
    assert body["screening_id"] == screening_id
