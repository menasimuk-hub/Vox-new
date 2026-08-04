"""Requester email preferred over platform actor for support notify/display."""

from types import SimpleNamespace

from app.services.support_ticket_service import ticket_requester_email, _normalize_requester_email


def test_normalize_requester_email():
    assert _normalize_requester_email("  Ada@Example.com ") == "ada@example.com"
    assert _normalize_requester_email("not-an-email") is None
    assert _normalize_requester_email("") is None


def test_ticket_requester_email_prefers_explicit(monkeypatch):
    ticket = SimpleNamespace(requester_email="customer@example.com", created_by_user_id="u1")

    class FakeDb:
        def get(self, *_a, **_k):
            return SimpleNamespace(email="aoi-account@voxbulk.com")

    assert ticket_requester_email(FakeDb(), ticket) == "customer@example.com"


def test_ticket_requester_email_falls_back_to_creator():
    ticket = SimpleNamespace(requester_email=None, created_by_user_id="u1")

    class FakeDb:
        def get(self, *_a, **_k):
            return SimpleNamespace(email="owner@org.com")

    assert ticket_requester_email(FakeDb(), ticket) == "owner@org.com"
