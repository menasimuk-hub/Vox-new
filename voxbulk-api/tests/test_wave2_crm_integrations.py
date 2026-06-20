"""Wave 2 CRM provider registry, exclusivity, and catalogue behaviour."""

from __future__ import annotations

import json

import pytest


def _seed_org(db):
    from app.models.organisation import Organisation

    org = Organisation(name="Wave2 Org")
    db.add(org)
    db.flush()
    db.commit()
    return org


def _seed_admin(db, *, provider: str, visible: bool = True, config: dict | None = None):
    from app.services.provider_settings import ProviderSettingsService

    cfg = config or {
        "client_id": "cid",
        "client_secret": "sec",
        "redirect_uri": "https://api.example.com/cb",
    }
    if provider == "hubspot":
        cfg = {"auth_mode": "oauth", **cfg}
    if provider == "zoho_crm":
        cfg["data_center"] = "com"
    ProviderSettingsService.upsert_platform_config(
        db,
        provider=provider,
        is_enabled=True,
        config=cfg,
        visible_to_orgs=visible,
    )


@pytest.fixture()
def session(app_client):  # noqa: ARG001
    from app.core.database import get_sessionmaker

    Session = get_sessionmaker()
    db = Session()
    try:
        yield db
    finally:
        db.close()


def test_crm_exclusivity_blocks_second_provider(session):
    from app.services.crm_connection_service import active_crm_provider, ensure_can_connect_crm, save_crm_config_raw

    org = _seed_org(session)
    save_crm_config_raw(
        session,
        org.id,
        "pipedrive",
        {"access_token": "tok", "refresh_token": "ref", "connected_at": "2026-01-01T00:00:00"},
    )
    assert active_crm_provider(session, org.id) == "pipedrive"
    with pytest.raises(ValueError, match="Disconnect Pipedrive"):
        ensure_can_connect_crm(session, org.id, "zoho_crm")
    ensure_can_connect_crm(session, org.id, "zoho_crm", replace=True)
    assert active_crm_provider(session, org.id) is None
    save_crm_config_raw(session, org.id, "zoho_crm", {"access_token": "zoho-tok"})
    assert active_crm_provider(session, org.id) == "zoho_crm"


def test_disconnect_crm_cascades_zoho_bookings(session):
    from app.services.crm_connection_service import disconnect_crm, save_crm_config_raw

    org = _seed_org(session)
    save_crm_config_raw(session, org.id, "zoho_crm", {"access_token": "tok"})
    org.scheduling_config_json = json.dumps(
        {"provider": "zoho_bookings", "service_url": "https://bookings.example/s/1"}
    )
    session.add(org)
    session.commit()
    disconnect_crm(session, org.id, provider="zoho_crm")
    session.refresh(org)
    assert org.zoho_crm_config_json is None
    assert org.scheduling_config_json is None


def test_catalogue_blocks_second_crm_and_missing_parent(session):
    from app.services.crm_connection_service import save_crm_config_raw
    from app.services.integration_catalogue_service import list_integrations_for_org

    org = _seed_org(session)
    for provider in ("pipedrive", "zoho_crm", "zoho_bookings", "hubspot", "cal_com"):
        _seed_admin(session, provider=provider)
    save_crm_config_raw(session, org.id, "pipedrive", {"access_token": "tok"})

    result = list_integrations_for_org(session, org.id)
    hubspot = next(r for r in result["crm"] if r["key"] == "hubspot")
    zoho_crm = next(r for r in result["crm"] if r["key"] == "zoho_crm")
    zoho_bookings = next(r for r in result["booking"] if r["key"] == "zoho_bookings")

    assert hubspot["blocked_reason"] and "Disconnect Pipedrive" in hubspot["blocked_reason"]
    assert zoho_crm["blocked_reason"] and "Disconnect Pipedrive" in zoho_crm["blocked_reason"]
    assert zoho_bookings["blocked_reason"] and "Connect Zoho CRM" in zoho_bookings["blocked_reason"]
    assert result["active_crm_provider"] == "pipedrive"


def test_catalogue_includes_wave2_providers_when_visible(session):
    from app.services.integration_catalogue_service import list_integrations_for_org

    org = _seed_org(session)
    for provider in ("pipedrive", "zoho_crm", "zoho_bookings"):
        _seed_admin(session, provider=provider)

    keys = {r["key"] for r in list_integrations_for_org(session, org.id)["crm"]}
    booking_keys = {r["key"] for r in list_integrations_for_org(session, org.id)["booking"]}
    assert "pipedrive" in keys
    assert "zoho_crm" in keys
    assert "zoho_bookings" in booking_keys
