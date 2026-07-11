"""Validate service-order recipient contact fields before DB write (friendly errors)."""
from __future__ import annotations

import re

PHONE_MAX_LEN = 64
NAME_MAX_LEN = 255
EMAIL_MAX_LEN = 255

_PHONE_OK = re.compile(r"^[\d\s\-().+/]+$")


def normalize_recipient_phone(raw: str | None, *, required: bool = False) -> str | None:
    """Strip and validate phone for service_order_recipients.phone (VARCHAR 64)."""
    phone = str(raw or "").strip()
    if not phone:
        if required:
            raise ValueError("Phone is required. Enter a mobile number with country code, e.g. +447700900123.")
        return None
    if len(phone) > PHONE_MAX_LEN:
        raise ValueError(
            f"Phone number is too long (max {PHONE_MAX_LEN} characters). "
            "Enter a normal mobile number with country code, e.g. +447700900123 — not notes or extra text."
        )
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 7 or len(digits) > 15:
        raise ValueError(
            "That does not look like a valid phone number. "
            "Use digits with an optional + country code (7–15 digits), e.g. +447700900123."
        )
    if not _PHONE_OK.match(phone):
        raise ValueError(
            "Phone can only contain digits, spaces, +, -, (, ) or /. "
            "Remove letters or other characters."
        )
    return phone


def normalize_recipient_name(raw: str | None, *, required: bool = True) -> str:
    name = str(raw or "").strip()
    if not name:
        if required:
            raise ValueError("Name is required.")
        return ""
    if len(name) > NAME_MAX_LEN:
        raise ValueError(f"Name is too long (max {NAME_MAX_LEN} characters). Shorten the name and try again.")
    return name


def normalize_recipient_email(raw: str | None) -> str | None:
    email = str(raw or "").strip()
    if not email:
        return None
    if len(email) > EMAIL_MAX_LEN:
        raise ValueError(f"Email is too long (max {EMAIL_MAX_LEN} characters).")
    if "@" not in email or "." not in email.split("@")[-1]:
        raise ValueError("Enter a valid email address, e.g. name@company.com.")
    return email
