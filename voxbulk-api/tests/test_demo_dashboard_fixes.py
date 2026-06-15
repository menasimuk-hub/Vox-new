"""Regression tests for demo dashboard home, scheduling disconnect, resend gate helpers."""

import json
import uuid

from app.core.security import hash_password


def _seed_org_with_interview(db):
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.service_order import ServiceOrderRecipient
    from app.models.user import User
    from app.services.platform_catalog_service import ServiceOrderService

    org = Organisation(name="Demo Dash Org")
    db.add(org)
    db.flush()
    user = User(email=f"dash-{uuid.uuid4().hex[:8]}@example.com", password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
    order = ServiceOrderService.create_order(
        db,
        org_id=org.id,
        user_id=user.id,
        service_code="interview",
        title="Demo Interview · Engineer · 2 candidates",
        config={"role": "Engineer", "demo_account_pack": "user_account_demo_v1"},
    )
    db.add(
        ServiceOrderRecipient(
            order_id=order.id,
            row_number=1,
            name="Alice",
            phone="+447700900001",
            email="alice@example.com",
            status="completed",
            result_json=json.dumps(
                {
                    "analysis_saved_at": "2026-01-01T12:00:00",
                    "analysis": {
                        "score": 88,
                        "recommendation": "Advance",
                        "sentiment": "Enthusiastic",
                        "short_summary": "Strong hire",
                    },
                }
            ),
        )
    )
    order.status = "completed"
    order.recipient_count = 1
    db.add(order)
    db.commit()
    return user, org, order


def test_home_summary_with_completed_interview(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org, order = _seed_org_with_interview(db)

    tok = app_client.post(
        "/auth/token",
        data={"username": user.email, "password": "pass123", "org_id": org.id},
    ).json()["access_token"]
    r = app_client.get("/dashboard/home-summary", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["interview"]["calls_completed"] >= 1
    assert payload["feedback"] is not None
    assert len(payload["feedback"]["recent"]) >= 1
    assert payload["feedback"]["sentiment"]["excellent"] >= 1


def test_disconnect_scheduling_clears_config():
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation
    from app.services.scheduling_connection_service import disconnect_scheduling, save_scheduling_config

    with get_sessionmaker()() as db:
        org = Organisation(name="Sched Org", scheduling_config_json='{"provider":"calendly","access_token":"enc:x"}')
        db.add(org)
        db.commit()
        db.refresh(org)
        save_scheduling_config(
            db,
            org.id,
            {"provider": "calendly", "access_token": "test-token", "event_type_uri": "https://calendly.com/x/30min"},
        )
        status = disconnect_scheduling(db, org.id, provider="calendly")
        assert status["connected"] is False
        assert status["calendly_connected"] is False


def test_interview_home_activity_snapshot_counts():
    from app.core.database import get_sessionmaker
    from app.services.interview_results_service import interview_home_activity_snapshot

    with get_sessionmaker()() as db:
        _user, org, _order = _seed_org_with_interview(db)
        snap = interview_home_activity_snapshot(db, org_id=org.id)
        assert snap["sentiment"]["excellent"] >= 1
        assert len(snap["recent"]) >= 1
        assert snap["recent"][0]["svc"] == "interviews"
