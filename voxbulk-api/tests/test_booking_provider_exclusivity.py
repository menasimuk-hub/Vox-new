"""Booking provider exclusivity and scheduling status labels."""

from __future__ import annotations

import json

from app.core.security import hash_password
from app.services.scheduling_connection_service import (
    get_scheduling_config,
    save_scheduling_config,
    scheduling_status,
)


def _seed_org(db):
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.user import User

    org = Organisation(name="Booking Org")
    db.add(org)
    db.flush()
    user = User(email="booking@test.local", password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    db.commit()
    return user, org


def _token(client, user, org_id):
    r = client.post("/auth/token", data={"username": user.email, "password": "pass123", "org_id": org_id})
    assert r.status_code == 200
    return r.json()["access_token"]


def test_scheduling_status_includes_provider_labels(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed_org(db)

    headers = {"Authorization": f"Bearer {_token(app_client, user, org.id)}"}
    st = app_client.get("/service-orders/scheduling/status", headers=headers)
    assert st.status_code == 200
    data = st.json()
    assert data.get("provider_label") is None
    assert data.get("connected_account") is None
    available = data.get("providers_available") or []
    assert "calendly" in available
    assert "microsoft_calendar" in available
    assert data.get("cronofy_connected") is False
    assert data.get("microsoft_calendar_connected") is False
    assert data.get("legacy_unsupported_provider") is None


def test_legacy_cronofy_marked_unsupported(app_client):
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    with get_sessionmaker()() as db:
        user, org = _seed_org(db)
        org_row = db.get(Organisation, org.id)
        org_row.scheduling_config_json = json.dumps(
            {
                "provider": "cronofy",
                "access_token": "enc:dummy",
                "owner_name": "Legacy User",
            }
        )
        db.add(org_row)
        db.commit()

    headers = {"Authorization": f"Bearer {_token(app_client, user, org.id)}"}
    st = app_client.get("/service-orders/scheduling/status", headers=headers)
    data = st.json()
    assert data.get("legacy_unsupported_provider") == "cronofy"
    assert data.get("human_scheduling_ready") is False
    assert data.get("connected") is False


def test_save_rejects_cronofy(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed_org(db)

    headers = {"Authorization": f"Bearer {_token(app_client, user, org.id)}"}
    with get_sessionmaker()() as db:
        try:
            save_scheduling_config(
                db,
                org.id,
                {"provider": "cronofy", "access_token": "x", "owner_name": "Test"},
            )
            assert False, "expected ValueError"
        except ValueError as exc:
            assert "no longer supported" in str(exc).lower()


def test_booking_provider_exclusivity_blocks_second_provider(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed_org(db)
        save_scheduling_config(
            db,
            org.id,
            {
                "provider": "calendly",
                "access_token": "token-a",
                "event_type_uri": "https://api.calendly.com/event_types/abc",
                "owner_name": "Jane",
            },
        )

    headers = {"Authorization": f"Bearer {_token(app_client, user, org.id)}"}
    start = app_client.get("/service-orders/scheduling/oauth/cal-com/start", headers=headers)
    assert start.status_code == 400
    assert "disconnect" in start.json().get("detail", "").lower()

    ms_start = app_client.get("/service-orders/scheduling/oauth/microsoft-calendar/start", headers=headers)
    assert ms_start.status_code == 400
    assert "disconnect" in ms_start.json().get("detail", "").lower()

    st = scheduling_status(get_sessionmaker()(), org.id)
    assert st.get("provider") == "calendly"
    assert st.get("provider_label") == "Calendly"
    assert st.get("connected_account") == "Jane"
    assert st.get("human_scheduling_ready") is True


def test_save_accepts_microsoft_calendar(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed_org(db)
        save_scheduling_config(
            db,
            org.id,
            {
                "provider": "microsoft_calendar",
                "access_token": "tok",
                "owner_name": "Jane",
                "schedule_url": "https://outlook.office365.com/owa/calendar/foo/bookings/",
            },
        )

    st = scheduling_status(get_sessionmaker()(), org.id)
    assert st.get("provider") == "microsoft_calendar"
    assert st.get("microsoft_calendar_connected") is True


def test_integrations_catalogue_route_not_order_lookup(app_client):
    """GET /service-orders/integrations must not be swallowed by /{order_id}."""
    from app.core.database import get_sessionmaker
    from app.services.provider_settings import ProviderSettingsService

    with get_sessionmaker()() as db:
        user, org = _seed_org(db)
        ProviderSettingsService.upsert_platform_config(
            db,
            provider="calendly",
            is_enabled=True,
            visible_to_orgs=True,
            config={
                "client_id": "x",
                "client_secret": "y",
                "redirect_uri": "https://example.com/cb",
            },
        )

    headers = {"Authorization": f"Bearer {_token(app_client, user, org.id)}"}
    res = app_client.get("/service-orders/integrations", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert "booking" in body
    assert "crm" in body
    assert any(row.get("key") == "calendly" for row in body.get("booking") or [])
