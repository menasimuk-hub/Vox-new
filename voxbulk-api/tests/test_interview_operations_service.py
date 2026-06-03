"""Tests for interview operations dashboard aggregation."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.interview_operations_service import (
    InterviewOperationsService,
    _aggregate_recipients,
    _delivery_health,
    _launch_status,
    _needs_attention,
    order_operations_row,
)


def _order(**kwargs) -> ServiceOrder:
    defaults = {
        "id": "ord-1",
        "org_id": "org-1",
        "user_id": "user-1",
        "service_code": "interview",
        "title": "Software Engineer",
        "reference_id": "INT-001",
        "status": "running",
        "payment_status": "approved",
        "recipient_count": 1,
        "quote_total_pence": 5000,
        "config_json": json.dumps(
            {
                "role": "Engineer",
                "launch_requested_at": "2026-06-01T10:00:00",
                "last_invite_dispatch": {"ok": True, "email_sent": 1, "whatsapp_sent": 0, "errors": []},
                "booking_invites_sent_at": "2026-06-01T10:01:00",
            }
        ),
        "report_json": json.dumps({"completed": 0, "reached": 0}),
        "started_at": datetime(2026, 6, 1, 10, 0, 0),
        "created_at": datetime(2026, 6, 1, 9, 0, 0),
        "updated_at": datetime(2026, 6, 1, 10, 5, 0),
    }
    defaults.update(kwargs)
    return ServiceOrder(**defaults)


def _recipient(**kwargs) -> ServiceOrderRecipient:
    defaults = {
        "id": "rec-1",
        "order_id": "ord-1",
        "row_number": 1,
        "name": "Alex Candidate",
        "phone": "+447700900123",
        "email": "alex@example.com",
        "status": "pending",
        "result_json": json.dumps(
            {
                "invite_email_sent_at": "2026-06-01T10:01:00",
                "invite_email_ok": True,
            }
        ),
        "created_at": datetime(2026, 6, 1, 9, 30, 0),
    }
    defaults.update(kwargs)
    return ServiceOrderRecipient(**defaults)


def test_launch_status_launched():
    order = _order()
    code, label = _launch_status(order, json.loads(order.config_json))
    assert code == "launched"
    assert label == "Launched"


def test_launch_status_waiting():
    order = _order(status="scheduled", started_at=None, config_json=json.dumps({"role": "Engineer"}))
    code, label = _launch_status(order, json.loads(order.config_json))
    assert code == "waiting"
    assert "Waiting" in label


def test_aggregate_recipients_email_sent():
    order = _order()
    agg = _aggregate_recipients(order, [_recipient()])
    assert agg["email_sent"] == 1
    assert agg["email_failed"] == 0
    assert "1/1 sent" in agg["email_label"]


def test_aggregate_recipients_email_failed():
    order = _order()
    recipient = _recipient(
        result_json=json.dumps({"invite_email_failed": "smtp_timeout", "invite_email_ok": False}),
    )
    agg = _aggregate_recipients(order, [recipient])
    assert agg["email_failed"] == 1
    assert agg["last_error"] == "smtp_timeout"
    assert any("Email failed" in reason for reason in agg["attention_reasons"])


def test_needs_attention_launch_failed():
    order = _order(
        config_json=json.dumps(
            {
                "launch_requested_at": "2026-06-01T10:00:00",
                "last_invite_dispatch": {"ok": False, "email_sent": 0, "errors": ["SMTP unavailable"]},
            }
        ),
    )
    agg = _aggregate_recipients(order, [_recipient(result_json="{}")])
    launch_code, _ = _launch_status(order, json.loads(order.config_json))
    flagged, reasons = _needs_attention(order, agg, launch_code, json.loads(order.config_json))
    assert flagged is True
    assert any("Launch" in r or "SMTP" in r for r in reasons)


def test_delivery_health_failed_when_email_failed():
    agg = {"email_state": "failed", "call_state": "pending", "attention_reasons": []}
    health = _delivery_health(agg, needs_attention=True, launch_code="launched")
    assert health == "failed"


def test_order_operations_row_includes_delivery_fields(monkeypatch):
    order = _order()
    recipient = _recipient()
    monkeypatch.setattr(
        "app.services.interview_operations_service.ServiceOrderService.order_to_dict",
        lambda order, **kwargs: {
            "id": order.id,
            "title": order.title,
            "reference_id": order.reference_id,
            "status": order.status,
            "status_label": "Running",
            "payment_status": order.payment_status,
            "recipient_count": 1,
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
            "is_live": True,
            "is_finished": False,
            "report": {"completed": 0},
        },
    )
    row = order_operations_row(None, order, [recipient], org_name="Acme Ltd", owner_email="owner@acme.com")
    assert row["org_name"] == "Acme Ltd"
    assert row["delivery_health"] in {"healthy", "partial", "failed", "stuck"}
    assert row["email_label"]
    assert "alex@example.com" in row["search_text"]
