"""Tests for recipient contact validation and friendly length errors."""
from __future__ import annotations

import pytest

from app.services.recipient_contact_validation import (
    normalize_recipient_email,
    normalize_recipient_name,
    normalize_recipient_phone,
)


def test_phone_rejects_too_long():
    with pytest.raises(ValueError, match="too long"):
        normalize_recipient_phone("scdwecwececeeeeeeeeeeeeeeeddddddddddddddddddddddddddddddddddddddddddddddddd")


def test_phone_rejects_letters():
    with pytest.raises(ValueError, match="digits"):
        normalize_recipient_phone("not-a-phone")


def test_phone_accepts_e164():
    assert normalize_recipient_phone("+447700900123") == "+447700900123"


def test_name_too_long():
    with pytest.raises(ValueError, match="too long"):
        normalize_recipient_name("x" * 300)


def test_email_invalid():
    with pytest.raises(ValueError, match="valid email"):
        normalize_recipient_email("not-an-email")
