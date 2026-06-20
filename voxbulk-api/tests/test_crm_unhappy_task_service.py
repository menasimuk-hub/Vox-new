"""Tests for optional CRM task on unhappy survey responses."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.crm_unhappy_task_service import (
    _crm_create_task_enabled,
    maybe_create_unhappy_crm_task,
)


def _recipient(**result: dict) -> ServiceOrderRecipient:
    row = ServiceOrderRecipient(
        order_id="ord-1",
        row_number=1,
        name="Alex Morgan",
        phone="+447700900123",
        email="alex@example.com",
        status="completed",
    )
    row.id = "rec-1"
    row.result_json = json.dumps(result, ensure_ascii=False)
    return row


def _order() -> ServiceOrder:
    order = ServiceOrder(
        org_id="org-1",
        service_code="survey",
        title="Post-visit feedback",
    )
    order.id = "ord-1"
    return order


def test_create_task_disabled_by_default():
    assert _crm_create_task_enabled({}) is False
    assert _crm_create_task_enabled({"create_task_on_unhappy_score": False}) is False
    assert _crm_create_task_enabled({"create_task_on_unhappy_score": True}) is True


def test_maybe_create_skips_when_not_unhappy():
    order = _order()
    recipient = _recipient(
        wa_conversation={"answers": [{"question": "How was it?", "answer": "Good", "step_role": "rating"}]}
    )
    db = MagicMock()
    with patch("app.services.crm_unhappy_task_service.active_crm_provider", return_value="pipedrive"):
        with patch("app.services.crm_unhappy_task_service._create_pipedrive_task") as create_mock:
            maybe_create_unhappy_crm_task(db, order, recipient)
            create_mock.assert_not_called()


def test_maybe_create_calls_provider_when_unhappy():
    order = _order()
    recipient = _recipient(
        wa_conversation={"answers": [{"question": "How was it?", "answer": "Bad", "step_role": "rating"}]}
    )
    db = MagicMock()
    with patch("app.services.crm_unhappy_task_service.active_crm_provider", return_value="pipedrive"):
        with patch("app.services.crm_unhappy_task_service._create_pipedrive_task") as create_mock:
            create_mock.return_value = {"ok": True, "skipped": True, "reason": "disabled"}
            maybe_create_unhappy_crm_task(db, order, recipient)
            create_mock.assert_called_once()


def test_maybe_create_skips_duplicate_task():
    order = _order()
    recipient = _recipient(
        crm_unhappy_task_created_at="2026-06-01T12:00:00",
        wa_conversation={"answers": [{"question": "How was it?", "answer": "Bad", "step_role": "rating"}]},
    )
    db = MagicMock()
    with patch("app.services.crm_unhappy_task_service.active_crm_provider", return_value="hubspot"):
        with patch("app.services.crm_unhappy_task_service._create_hubspot_task") as create_mock:
            maybe_create_unhappy_crm_task(db, order, recipient)
            create_mock.assert_not_called()
