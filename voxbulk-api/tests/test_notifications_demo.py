"""Dashboard notification triggers for demo readiness."""

from __future__ import annotations

from datetime import datetime

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.notification import Notification
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.models.user import User
from app.services.notification_service import NotificationService
from sqlalchemy import select


def _seed_user(app_client, *, email: str, superuser: bool = False):
    with get_sessionmaker()() as db:
        org = Organisation(name="Notify Demo Org")
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True, is_superuser=superuser)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        org_id = org.id
        user_id = user.id

    token = app_client.post("/auth/token", data={"username": email, "password": "pass123", "org_id": org_id}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}, org_id, user_id


def _admin_headers(app_client):
    return _seed_user(app_client, email="notify_admin@example.com", superuser=True)[0]


def test_admin_wallet_credit_creates_user_notification(app_client):
    user_headers, org_id, _user_id = _seed_user(app_client, email="notify_wallet_user@example.com")
    admin_headers = _admin_headers(app_client)

    before = app_client.get("/notifications/unread-count", headers=user_headers)
    assert before.status_code == 200

    credited = app_client.post(
        f"/admin/organisations/{org_id}/wallet/credit",
        headers=admin_headers,
        json={"amount_pence": 2500, "note": "Demo top-up"},
    )
    assert credited.status_code == 200, credited.text

    unread = app_client.get("/notifications/unread-count", headers=user_headers)
    assert unread.status_code == 200
    assert unread.json()["count"] >= 1

    rows = app_client.get("/notifications?unread_only=true", headers=user_headers)
    assert rows.status_code == 200
    wallet_rows = [r for r in rows.json() if r.get("type") == "wallet_credit"]
    assert wallet_rows, rows.json()
    assert wallet_rows[0]["action_url"] == "/account/billing"

    notif_id = wallet_rows[0]["id"]
    marked = app_client.post(f"/notifications/{notif_id}/read", headers=user_headers)
    assert marked.status_code == 200

    after = app_client.get("/notifications/unread-count", headers=user_headers)
    assert after.json()["count"] == before.json()["count"]


def test_ticket_reply_notification_action_url(app_client):
    user_headers, _org_id, _user_id = _seed_user(app_client, email="notify_ticket_user@example.com")
    admin_headers = _admin_headers(app_client)

    created = app_client.post(
        "/support/tickets",
        json={"category": "technical", "subject": "Notification deep link", "message": "Help"},
        headers=user_headers,
    )
    assert created.status_code == 200
    ticket_id = created.json()["id"]

    reply = app_client.post(
        f"/admin/support/tickets/{ticket_id}/reply",
        json={"message": "We replied."},
        headers=admin_headers,
    )
    assert reply.status_code == 200

    rows = app_client.get("/notifications?unread_only=true", headers=user_headers)
    assert rows.status_code == 200
    ticket_rows = [r for r in rows.json() if r.get("type") == "ticket_reply"]
    assert ticket_rows
    assert ticket_rows[0]["action_url"] == f"/account/support/tickets?ticket={ticket_id}"


def test_mark_all_notifications_read(app_client):
    user_headers, org_id, _user_id = _seed_user(app_client, email="notify_clear_all@example.com")
    admin_headers = _admin_headers(app_client)

    credited = app_client.post(
        f"/admin/organisations/{org_id}/wallet/credit",
        headers=admin_headers,
        json={"amount_pence": 500, "note": "First"},
    )
    assert credited.status_code == 200, credited.text

    before = app_client.get("/notifications/unread-count", headers=user_headers)
    assert before.status_code == 200
    assert before.json()["count"] >= 1

    cleared = app_client.post("/notifications/read-all", headers=user_headers)
    assert cleared.status_code == 200
    assert cleared.json()["marked"] >= 1

    after = app_client.get("/notifications/unread-count", headers=user_headers)
    assert after.status_code == 200
    assert after.json()["count"] == 0


def test_campaign_completed_notification_service():
    with get_sessionmaker()() as db:
        org = Organisation(name="Campaign Notify Org")
        db.add(org)
        db.flush()
        user = User(email="campaign_notify@example.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        order = ServiceOrder(
            org_id=org.id,
            user_id=user.id,
            service_code="survey",
            title="Demo survey campaign",
            status="completed",
            payment_status="approved",
            completed_at=datetime.utcnow(),
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        row = NotificationService.create_campaign_completed_notification(db, order=order)
        db.commit()
        assert row is not None
        assert row.type == "campaign_completed"
        assert row.action_url == f"/surveys/results?orderId={order.id}"

        saved = db.execute(select(Notification).where(Notification.dedupe_key == f"campaign-complete:{order.id}")).scalar_one()
        assert saved.title == "Survey campaign complete"
        assert saved.message == "Demo survey campaign"
