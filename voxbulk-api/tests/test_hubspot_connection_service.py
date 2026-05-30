"""Tests for HubSpot OAuth config and candidate sync."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrderRecipient
from app.models.user import User
from app.services.hubspot_connection_service import (
    hubspot_oauth_start,
    hubspot_status,
    platform_oauth_configured,
    save_hubspot_config,
    sync_recipient_to_hubspot,
    verify_hubspot_platform_config,
)
from app.services.platform_catalog_service import ServiceOrderService


@pytest.fixture()
def db_session():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def test_hubspot_platform_config_requires_credentials(db_session: Session):
    with patch(
        "app.services.hubspot_connection_service._hubspot_platform_credentials",
        return_value=("", "", ""),
    ):
        result = verify_hubspot_platform_config(db_session)
    assert result["ok"] is False


def test_hubspot_oauth_start_builds_authorize_url(db_session: Session):
    org = Organisation(name="HubSpot Org")
    db_session.add(org)
    db_session.commit()
    with patch(
        "app.services.hubspot_connection_service._hubspot_platform_auth_mode",
        return_value="oauth",
    ), patch(
        "app.services.hubspot_connection_service._hubspot_platform_credentials",
        return_value=("client-abc", "secret", "https://api.test/hubspot/oauth/callback"),
    ):
        url = hubspot_oauth_start(org_id=org.id, db=db_session)
    assert "app.hubspot.com/oauth/authorize" in url
    assert "client_id=client-abc" in url
    assert org.id in url


def test_hubspot_status_connected(db_session: Session):
    org = Organisation(name="Connected HubSpot Org")
    db_session.add(org)
    db_session.flush()
    save_hubspot_config(
        db_session,
        org.id,
        {
            "access_token": "token-123",
            "refresh_token": "refresh-123",
            "hub_id": "999",
            "hub_domain": "example.hubspot.com",
            "account_name": "Recruiter",
        },
    )
    status = hubspot_status(db_session, org.id)
    assert status["connected"] is True
    assert status["hub_id"] == "999"
    assert status["auto_sync_shortlist"] is True


def test_sync_recipient_creates_contact(db_session: Session):
    org = Organisation(name="Sync Org")
    user = User(email=f"hub-{uuid.uuid4().hex[:8]}@test.com", password_hash="x", is_active=True)
    db_session.add(org)
    db_session.add(user)
    db_session.flush()
    save_hubspot_config(db_session, org.id, {"access_token": "tok", "refresh_token": "ref", "hub_id": "42"})
    order = ServiceOrderService.create_order(
        db_session,
        org_id=org.id,
        user_id=user.id,
        service_code="interview",
        title="Developer",
        config={"role": "Developer"},
    )
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Jane Doe",
        email="jane@example.com",
        phone="+447700900123",
        status="completed",
        ats_score=85,
    )
    db_session.add(recipient)
    db_session.commit()

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"id": "contact-777"}

    search_response = MagicMock()
    search_response.status_code = 200
    search_response.json.return_value = {"results": []}

    with patch("app.services.hubspot_connection_service._ensure_access_token", return_value="tok"):
        with patch("httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.post.side_effect = [search_response, mock_response]
            result = sync_recipient_to_hubspot(
                db_session,
                org.id,
                order=order,
                recipient=recipient,
                scheduling_url="https://calendly.com/x",
            )

    assert result["ok"] is True
    assert result["contact_id"] == "contact-777"
    assert "hubspot_contact_id" in (recipient.result_json or "")


def test_platform_oauth_configured_with_env(monkeypatch):
    monkeypatch.setenv("HUBSPOT_CLIENT_ID", "cid")
    monkeypatch.setenv("HUBSPOT_CLIENT_SECRET", "sec")
    monkeypatch.setenv("HUBSPOT_REDIRECT_URI", "https://api.test/cb")
    from app.core.config import get_settings

    get_settings.cache_clear()
    assert platform_oauth_configured(None) is True
    get_settings.cache_clear()


def test_hubspot_private_app_platform_config(db_session: Session):
    from app.services.provider_settings import ProviderSettingsService

    ProviderSettingsService.upsert_platform_config(
        db_session,
        provider="hubspot",
        is_enabled=True,
        config={"auth_mode": "private_app"},
    )
    result = verify_hubspot_platform_config(db_session)
    assert result["ok"] is True
    assert result.get("auth_mode") == "private_app"
    assert platform_oauth_configured(db_session) is True
