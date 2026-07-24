"""HubSpot Meetings / Zoho Bookings URL-only connect."""

from __future__ import annotations

import pytest


@pytest.fixture()
def session(app_client):  # noqa: ARG001
    from app.core.database import get_sessionmaker

    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()


def _seed_org(db):
    from app.models.organisation import Organisation

    org = Organisation(name="Booking URL Org")
    db.add(org)
    db.flush()
    db.commit()
    return org


def test_hubspot_meetings_connect_by_url_without_crm(session):
    from app.services.hubspot_meetings_service import (
        connect_hubspot_meetings,
        create_hubspot_meetings_scheduling_link,
    )
    from app.services.scheduling_connection_service import get_scheduling_config

    org = _seed_org(session)
    connect_hubspot_meetings(
        session,
        org.id,
        meeting_link_url="https://meetings.hubspot.com/acme/intro",
        meeting_link_name="Intro",
    )
    cfg = get_scheduling_config(session, org.id)
    assert cfg["provider"] == "hubspot_meetings"
    assert cfg["connection_mode"] == "url"
    assert cfg["meeting_link_url"].startswith("https://")

    link = create_hubspot_meetings_scheduling_link(
        session, org.id, candidate_name="Ada Lovelace", candidate_email="ada@example.com"
    )
    assert "meetings.hubspot.com" in link
    assert "email=" in link


def test_zoho_bookings_connect_by_url_without_crm(session):
    from app.services.scheduling_connection_service import get_scheduling_config
    from app.services.zoho_bookings_service import (
        connect_zoho_bookings,
        create_zoho_bookings_scheduling_link,
    )

    org = _seed_org(session)
    connect_zoho_bookings(
        session,
        org.id,
        service_url="https://bookings.zoho.com/portal/acme",
        service_name="Screening",
    )
    cfg = get_scheduling_config(session, org.id)
    assert cfg["provider"] == "zoho_bookings"
    assert cfg["connection_mode"] == "url"
    link = create_zoho_bookings_scheduling_link(session, org.id, candidate_name="Bob", candidate_email="b@x.com")
    assert "bookings.zoho.com" in link
