"""Tests for Telnyx number inventory service."""

from __future__ import annotations

from app.services.telnyx_number_inventory_service import (
    _collect_configured_senders,
    build_number_inventory,
)


def test_collect_configured_senders_from_routes():
    config = {
        "voice_routes": [{"number": "+442046203055", "regions": ["gb"], "label": "UK landline"}],
        "whatsapp_routes": [{"number": "+447822002055", "regions": ["global"], "label": "WA mobile"}],
        "sms_from": "+447700900123",
    }
    senders = _collect_configured_senders(config)
    numbers_roles = {(s["number"], s["role"]) for s in senders}
    assert ("+442046203055", "voice") in numbers_roles
    assert ("+447822002055", "whatsapp") in numbers_roles
    assert ("+447700900123", "sms") in numbers_roles


def test_build_number_inventory_marks_missing(monkeypatch):
    def fake_list(*, api_key: str):
        return [{"id": "pn-1", "phone_number": "+442046203055", "connection_id": "conn-abc"}]

    def fake_msg(*, api_key: str, phone: str):
        return None

    monkeypatch.setattr(
        "app.services.telnyx_number_inventory_service.list_account_phone_records",
        fake_list,
    )
    monkeypatch.setattr(
        "app.services.telnyx_number_inventory_service._messaging_profile_for_number",
        fake_msg,
    )

    config = {
        "connection_id": "conn-abc",
        "voice_routes": [{"number": "+442046203055", "regions": ["gb"], "label": "Landline"}],
        "whatsapp_routes": [{"number": "+447822002099", "regions": ["global"], "label": "Missing WA"}],
    }
    inv = build_number_inventory(api_key="KEY_test", config=config)
    assert "+442046203055" in inv["telnyx_phone_numbers"]
    checks = {c["number"]: c for c in inv["configured_checks"]}
    assert checks["+442046203055"]["status"] == "ok"
    assert checks["+447822002099"]["on_account"] is False
    assert inv["ok"] is False
