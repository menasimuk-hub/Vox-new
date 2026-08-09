"""Smart Card contact reply parsing — emails must not become names."""

from __future__ import annotations

from app.services.smart_card.session_flow_service import (
    PRODUCT_MENU_STEPS,
    _apply_contact_reply,
)


def test_lone_email_sets_visitor_email_not_name():
    state: dict = {}
    _apply_contact_reply(state, "Daddyservicesltd@gmail.com")
    assert state.get("visitor_email") == "Daddyservicesltd@gmail.com"
    assert "name" not in state


def test_email_with_label_sets_email():
    state: dict = {}
    _apply_contact_reply(state, "email Daddyservicesltd@gmail.com")
    assert state.get("visitor_email") == "Daddyservicesltd@gmail.com"
    assert "name" not in state


def test_pipe_format_still_works():
    state: dict = {}
    _apply_contact_reply(state, "Ana Diaz | Acme Ltd | ana@acme.test | +447700900111")
    assert state["name"] == "Ana Diaz"
    assert state["company"] == "Acme Ltd"
    assert state["visitor_email"] == "ana@acme.test"
    assert state["visitor_phone"] == "+447700900111"


def test_email_first_in_pipe_does_not_become_name():
    state: dict = {"name": "Old Name", "visitor_email": "old@example.com"}
    _apply_contact_reply(state, "new@example.com | Acme")
    assert state["visitor_email"] == "new@example.com"
    assert state["company"] == "Acme"
    assert state["name"] == "Old Name"


def test_plain_name_still_sets_name():
    state: dict = {}
    _apply_contact_reply(state, "Qusay")
    assert state["name"] == "Qusay"
    assert "visitor_email" not in state


def test_consent_info_not_product_menu():
    assert "consent_info" not in PRODUCT_MENU_STEPS
    assert "products_wanted" in PRODUCT_MENU_STEPS
