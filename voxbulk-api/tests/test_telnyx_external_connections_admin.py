from __future__ import annotations

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User


def _admin_headers(app_client):
    with get_sessionmaker()() as db:
        org = Organisation(name="Telnyx External Org")
        db.add(org)
        db.flush()
        user = User(
            email="telnyx_external_admin@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
            is_superuser=True,
        )
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        org_id = org.id
        email = user.email
    token = app_client.post(
        "/auth/token",
        data={"username": email, "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_admin_telnyx_minimal_save(app_client):
    headers = _admin_headers(app_client)
    res = app_client.put(
        "/admin/integrations/telnyx",
        json={
            "is_enabled": True,
            "config": {
                "api_key": "KEY" + "a" * 55,
                "connection_id": "conn-123",
                "default_outbound_number": "+15550001111",
                "voice_webhook_url": "https://api.voxbulk.com/telnyx/webhooks/voice",
                "status_callback_url": "https://api.voxbulk.com/telnyx/webhooks/status",
                "messaging_webhook_url": "https://api.voxbulk.com/telnyx/webhooks/messages",
            },
        },
        headers=headers,
    )
    assert res.status_code == 200
