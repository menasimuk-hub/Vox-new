"""Consent list export columns include name, email, service opt-in."""

from __future__ import annotations

from app.services.customer_feedback.consent_events_service import (
    EXPORT_COLUMNS,
    _purpose_label,
    _session_contact,
)


def test_export_columns_lead_with_name_email_service_optin():
    assert EXPORT_COLUMNS[:4] == ["name", "email", "phone_number", "service_optin"]
    assert "timestamp" in EXPORT_COLUMNS


def test_purpose_labels():
    assert _purpose_label("callback_call") == "Callback opt-in"
    assert _purpose_label("marketing") == "Marketing opt-in"


def test_session_contact_from_state():
    name, email = _session_contact({"visitor_name": "Ada", "email": "ada@example.com"})
    assert name == "Ada"
    assert email == "ada@example.com"
