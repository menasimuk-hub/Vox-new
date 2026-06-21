"""Visibility matrix for IntegrationCatalogueService."""

from __future__ import annotations

import json

import pytest

from app.core.security import hash_password


def _seed_org(db):
    from app.models.organisation import Organisation

    org = Organisation(name="Catalogue Org")
    db.add(org)
    db.flush()
    db.commit()
    return org


def _seed_admin_row(db, *, provider: str, is_enabled: bool, visible: bool, config: dict | None = None):
    from app.services.provider_settings import ProviderSettingsService

    cfg = config or {}
    if provider == "hubspot" and not cfg:
        cfg = {"auth_mode": "private_app"}
    ProviderSettingsService.upsert_platform_config(
        db,
        provider=provider,
        is_enabled=is_enabled,
        config=cfg,
        visible_to_orgs=visible,
    )


def _list_keys(catalogue: dict, group: str) -> set[str]:
    return {row["key"] for row in catalogue.get(group, [])}


@pytest.fixture()
def session(app_client):  # noqa: ARG001  — app_client fixture rebuilds schema
    from app.core.database import get_sessionmaker

    Session = get_sessionmaker()
    db = Session()
    try:
        yield db
    finally:
        db.close()


def test_hidden_when_admin_disabled(session):
    from app.services.integration_catalogue_service import list_integrations_for_org

    org = _seed_org(session)
    _seed_admin_row(
        session,
        provider="calendly",
        is_enabled=False,
        visible=True,
        config={"client_id": "x", "client_secret": "y", "redirect_uri": "https://a/cb"},
    )

    result = list_integrations_for_org(session, org.id)
    assert "calendly" not in _list_keys(result, "booking")


def test_hidden_when_visible_to_orgs_off(session):
    from app.services.integration_catalogue_service import list_integrations_for_org

    org = _seed_org(session)
    _seed_admin_row(
        session,
        provider="calendly",
        is_enabled=True,
        visible=False,
        config={"client_id": "x", "client_secret": "y", "redirect_uri": "https://a/cb"},
    )

    result = list_integrations_for_org(session, org.id)
    assert "calendly" not in _list_keys(result, "booking")


def test_visible_when_both_flags_on(session):
    from app.services.integration_catalogue_service import list_integrations_for_org

    org = _seed_org(session)
    _seed_admin_row(
        session,
        provider="calendly",
        is_enabled=True,
        visible=True,
        config={"client_id": "x", "client_secret": "y", "redirect_uri": "https://a/cb"},
    )

    result = list_integrations_for_org(session, org.id)
    assert "calendly" in _list_keys(result, "booking")
    cal = next(row for row in result["booking"] if row["key"] == "calendly")
    assert cal["platform_ready"] is True
    assert cal["visible_to_orgs"] is True
    assert cal["connected"] is False


def test_connected_status_reflects_org_scheduling_config(session):
    from app.models.organisation import Organisation
    from app.services.integration_catalogue_service import list_integrations_for_org

    org = _seed_org(session)
    _seed_admin_row(
        session,
        provider="calendly",
        is_enabled=True,
        visible=True,
        config={"client_id": "x", "client_secret": "y", "redirect_uri": "https://a/cb"},
    )
    org_row = session.get(Organisation, org.id)
    org_row.scheduling_config_json = json.dumps(
        {
            "provider": "calendly",
            "access_token": "token-a",
            "owner_name": "Jane",
            "event_type_uri": "https://api.calendly.com/event_types/x",
        }
    )
    session.add(org_row)
    session.commit()

    result = list_integrations_for_org(session, org.id)
    cal = next(row for row in result["booking"] if row["key"] == "calendly")
    assert cal["connected"] is True
    assert cal["connected_account"] == "Jane"
    assert result["active_booking_provider"] == "calendly"


def test_other_booking_provider_blocked_when_one_is_active(session):
    from app.models.organisation import Organisation
    from app.services.integration_catalogue_service import list_integrations_for_org

    org = _seed_org(session)
    for key in ("calendly", "cal_com"):
        _seed_admin_row(
            session,
            provider=key,
            is_enabled=True,
            visible=True,
            config={"client_id": "x", "client_secret": "y", "redirect_uri": f"https://a/{key}/cb"},
        )
    org_row = session.get(Organisation, org.id)
    org_row.scheduling_config_json = json.dumps(
        {"provider": "calendly", "access_token": "t", "event_type_uri": "https://api.calendly.com/event_types/x"}
    )
    session.add(org_row)
    session.commit()

    result = list_integrations_for_org(session, org.id)
    cal_com = next(row for row in result["booking"] if row["key"] == "cal_com")
    assert cal_com["blocked_reason"]
    assert "Another booking provider" in cal_com["blocked_reason"]


def test_microsoft_calendar_appears_when_admin_flips_visible(session):
    from app.services.integration_catalogue_service import list_integrations_for_org

    org = _seed_org(session)
    _seed_admin_row(
        session,
        provider="microsoft_calendar",
        is_enabled=True,
        visible=False,
        config={
            "client_id": "ms-client",
            "client_secret": "ms-secret",
            "redirect_uri": "https://a/ms/cb",
            "tenant": "common",
        },
    )
    soft_launch = list_integrations_for_org(session, org.id)
    assert "microsoft_calendar" not in _list_keys(soft_launch, "booking")

    _seed_admin_row(
        session,
        provider="microsoft_calendar",
        is_enabled=True,
        visible=True,
        config={
            "client_id": "ms-client",
            "client_secret": "ms-secret",
            "redirect_uri": "https://a/ms/cb",
            "tenant": "common",
        },
    )
    live = list_integrations_for_org(session, org.id)
    assert "microsoft_calendar" in _list_keys(live, "booking")


def test_microsoft_catalogue_connected_with_encrypted_token(session):
    from app.services.integration_catalogue_service import list_integrations_for_org
    from app.services.scheduling_connection_service import save_scheduling_config

    org = _seed_org(session)
    _seed_admin_row(
        session,
        provider="microsoft_calendar",
        is_enabled=True,
        visible=True,
        config={
            "client_id": "ms-client",
            "client_secret": "ms-secret",
            "redirect_uri": "https://a/ms/cb",
            "tenant": "common",
        },
    )
    save_scheduling_config(
        session,
        org.id,
        {
            "provider": "microsoft_calendar",
            "access_token": "ms-token-plain",
            "owner_name": "Jane",
            "owner_email": "jane@example.com",
            "schedule_url": "https://outlook.office365.com/owa/calendar/foo/bookings/",
        },
    )

    result = list_integrations_for_org(session, org.id)
    ms = next(row for row in result["booking"] if row["key"] == "microsoft_calendar")
    assert ms["connected"] is True
    assert ms["connected_account"] == "Jane · jane@example.com"
    assert ms["extra"]["event_type_configured"] is True
    assert ms["extra"]["human_scheduling_ready"] is True
    assert result["active_booking_provider"] == "microsoft_calendar"


def test_microsoft_catalogue_oauth_without_schedule_url(session):
    from app.services.integration_catalogue_service import list_integrations_for_org
    from app.services.scheduling_connection_service import save_scheduling_config

    org = _seed_org(session)
    _seed_admin_row(
        session,
        provider="microsoft_calendar",
        is_enabled=True,
        visible=True,
        config={
            "client_id": "ms-client",
            "client_secret": "ms-secret",
            "redirect_uri": "https://a/ms/cb",
            "tenant": "common",
        },
    )
    save_scheduling_config(
        session,
        org.id,
        {
            "provider": "microsoft_calendar",
            "access_token": "ms-token-plain",
            "owner_name": "Jane",
            "schedule_url": "",
        },
    )

    result = list_integrations_for_org(session, org.id)
    ms = next(row for row in result["booking"] if row["key"] == "microsoft_calendar")
    assert ms["connected"] is True
    assert ms["extra"]["event_type_configured"] is False
    assert ms["extra"]["human_scheduling_ready"] is False


def test_microsoft_catalogue_disconnected_when_token_decrypt_fails(session):
    from app.models.organisation import Organisation
    from app.services.integration_catalogue_service import list_integrations_for_org

    org = _seed_org(session)
    _seed_admin_row(
        session,
        provider="microsoft_calendar",
        is_enabled=True,
        visible=True,
        config={
            "client_id": "ms-client",
            "client_secret": "ms-secret",
            "redirect_uri": "https://a/ms/cb",
            "tenant": "common",
        },
    )
    org_row = session.get(Organisation, org.id)
    org_row.scheduling_config_json = json.dumps(
        {
            "provider": "microsoft_calendar",
            "access_token": "enc:not-a-valid-fernet-token",
            "owner_name": "Jane",
        }
    )
    session.add(org_row)
    session.commit()

    result = list_integrations_for_org(session, org.id)
    ms = next(row for row in result["booking"] if row["key"] == "microsoft_calendar")
    assert ms["connected"] is True
    assert ms["extra"]["token_decrypt_failed"] is True


def test_microsoft_schedule_save_preserves_encrypted_token_when_decrypt_fails(session):
    from app.models.organisation import Organisation
    from app.services.microsoft_calendar_service import select_microsoft_calendar_schedule

    org = _seed_org(session)
    org_row = session.get(Organisation, org.id)
    org_row.scheduling_config_json = json.dumps(
        {
            "provider": "microsoft_calendar",
            "access_token": "enc:not-a-valid-fernet-token",
            "owner_name": "Jane",
        }
    )
    session.add(org_row)
    session.commit()

    select_microsoft_calendar_schedule(
        session,
        org.id,
        schedule_url="https://outlook.office365.com/owa/calendar/foo/bookings/",
    )
    stored = json.loads(session.get(Organisation, org.id).scheduling_config_json or "{}")
    assert stored["access_token"] == "enc:not-a-valid-fernet-token"
    assert stored["schedule_url"].startswith("https://outlook.office365.com/")
