"""Tests for recipient contact validation and friendly length errors."""
from __future__ import annotations

import pytest

from app.services.recipient_contact_validation import (
    coerce_interview_phone_e164,
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


def test_coerce_interview_phone_uk_local():
    e164, err = coerce_interview_phone_e164("07700900123")
    assert err is None
    assert e164 == "+447700900123"


def test_coerce_interview_phone_digits_without_plus():
    e164, err = coerce_interview_phone_e164("447700900123")
    assert err is None
    assert e164 == "+447700900123"


def test_coerce_interview_phone_invalid():
    e164, err = coerce_interview_phone_e164("12")
    assert e164 == "12"
    assert err


def test_name_too_long():
    with pytest.raises(ValueError, match="too long"):
        normalize_recipient_name("x" * 300)


def test_email_invalid():
    with pytest.raises(ValueError, match="valid email"):
        normalize_recipient_email("not-an-email")
