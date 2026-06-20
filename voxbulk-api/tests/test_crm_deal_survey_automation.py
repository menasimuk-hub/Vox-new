"""Tests for CRM deal-stage survey automation."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.service_order import ServiceOrder
from app.services.crm_deal_survey_automation_service import (
    CrmDealSurveyAutomationError,
    crm_automation_enabled,
    dry_run_crm_automation,
    read_crm_automation_config,
    survey_crm_automation_blocks_auto_complete,
    update_crm_automation_settings,
)
from tests.test_wave2_crm_integrations import _seed_org


@pytest.fixture()
def session(app_client):  # noqa: ARG001
    from app.core.database import get_sessionmaker

    Session = get_sessionmaker()
    db = Session()
    try:
        yield db
    finally:
        db.close()


def _survey_order(db, org_id: str, *, config: dict | None = None) -> ServiceOrder:
    cfg = config or {}
    order = ServiceOrder(
        id=str(uuid.uuid4()),
        org_id=org_id,
        user_id=str(uuid.uuid4()),
        service_code="survey",
        title="Post-service feedback",
        status="running",
        payment_status="approved",
        config_json=json.dumps(cfg),
    )
    db.add(order)
    db.commit()
    return order


def test_read_crm_automation_config_empty(session):
    org = _seed_org(session)
    order = _survey_order(session, org.id)
    assert read_crm_automation_config(order) == {}
    assert crm_automation_enabled(order) is False


def test_survey_crm_automation_blocks_auto_complete(session):
    org = _seed_org(session)
    order = _survey_order(
        session,
        org.id,
        config={"crm_automation": {"enabled": True, "stage_ids": ["1"]}},
    )
    assert survey_crm_automation_blocks_auto_complete(order) is True
    order.status = "draft"
    assert survey_crm_automation_blocks_auto_complete(order) is False


@patch("app.services.crm_deal_survey_automation_service.active_crm_provider", return_value="pipedrive")
@patch("app.services.crm_deal_survey_automation_service._subscription_allows_automation", return_value=(True, None))
def test_update_crm_automation_requires_consent(mock_sub, mock_provider, session):
    org = _seed_org(session)
    order = _survey_order(session, org.id)
    with pytest.raises(CrmDealSurveyAutomationError, match="consent"):
        update_crm_automation_settings(
            session,
            org.id,
            order=order,
            enabled=True,
            stage_ids=["5"],
            consent_acknowledged=False,
        )


@patch("app.services.crm_deal_survey_automation_service.active_crm_provider", return_value="pipedrive")
@patch("app.services.crm_deal_survey_automation_service._subscription_allows_automation", return_value=(True, None))
def test_update_crm_automation_saves_settings(mock_sub, mock_provider, session):
    org = _seed_org(session)
    order = _survey_order(session, org.id)
    result = update_crm_automation_settings(
        session,
        org.id,
        order=order,
        enabled=True,
        stage_ids=["5", "6"],
        delay_hours=12,
        consent_acknowledged=True,
    )
    assert result["enabled"] is True
    assert result["stage_ids"] == ["5", "6"]
    assert result["delay_hours"] == 12
    session.refresh(order)
    assert read_crm_automation_config(order)["enabled"] is True


@patch("app.services.crm_deal_survey_automation_service._fetch_pipedrive_deals_for_stages")
@patch("app.services.crm_deal_survey_automation_service._ensure_access_token", return_value="token")
@patch("app.services.crm_deal_survey_automation_service._stage_name_map", return_value={"5": "Won"})
@patch("app.services.crm_deal_survey_automation_service._fetch_pipedrive_person")
def test_dry_run_skips_missing_phone(mock_person, mock_stages, mock_token, mock_deals, session):
    org = _seed_org(session)
    order = _survey_order(
        session,
        org.id,
        config={"crm_automation": {"provider": "pipedrive", "stage_ids": ["5"], "delay_hours": 0}},
    )
    mock_deals.return_value = [
        {
            "id": 101,
            "title": "Acme deal",
            "stage_id": 5,
            "person_id": 9,
            "stage_change_time": datetime.utcnow().isoformat(),
        }
    ]
    mock_person.return_value = {"name": "Jane", "phone": [], "email": []}
    result = dry_run_crm_automation(session, org.id, order)
    assert result["would_skip"] == 1
    assert result["rows"][0]["reason"] == "missing_phone"


@patch("app.services.crm_deal_survey_automation_service._fetch_pipedrive_deals_for_stages")
@patch("app.services.crm_deal_survey_automation_service._ensure_access_token", return_value="token")
@patch("app.services.crm_deal_survey_automation_service._stage_name_map", return_value={"5": "Won"})
@patch("app.services.crm_deal_survey_automation_service._fetch_pipedrive_person")
def test_dry_run_schedules_with_phone(mock_person, mock_stages, mock_token, mock_deals, session):
    org = _seed_org(session)
    order = _survey_order(
        session,
        org.id,
        config={"crm_automation": {"provider": "pipedrive", "stage_ids": ["5"], "delay_hours": 0}},
    )
    mock_deals.return_value = [
        {
            "id": 102,
            "title": "Beta deal",
            "stage_id": 5,
            "person_id": 10,
            "stage_change_time": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
        }
    ]
    mock_person.return_value = {"name": "Sam", "phone": [{"value": "+447700900123", "primary": True}]}
    result = dry_run_crm_automation(session, org.id, order)
    assert result["would_schedule"] == 1
    assert result["rows"][0]["action"] == "schedule"
