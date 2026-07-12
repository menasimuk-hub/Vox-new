"""Validate service-order recipient contact fields before DB write (friendly errors)."""
from __future__ import annotations

import re
import unicodedata

PHONE_MAX_LEN = 64
NAME_MAX_LEN = 255
EMAIL_MAX_LEN = 255

_PHONE_OK = re.compile(r"^[\d\s\-().+/]+$")
# Common Excel / CRM prefixes before a real number.
_PHONE_PREFIX = re.compile(
    r"^(?:tel(?:ephone)?|mobile|mob|whatsapp|wa|phone|cell|call|fax)\s*[:：.\-]?\s*",
    re.IGNORECASE,
)
# Invisible / bidirectional marks that Excel pastes into phone cells.
_INVISIBLE = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\ufeff\u2060\u00ad]")


def sanitize_phone_input(raw: str | None) -> str:
    """Clean Excel/CRM junk while keeping a dialable number shape."""
    phone = unicodedata.normalize("NFKC", str(raw or "")).strip()
    if not phone:
        return ""
    phone = _INVISIBLE.sub("", phone)
    phone = phone.replace("\u00a0", " ").replace("\u202f", " ").replace("\u2007", " ")
    phone = phone.replace("–", "-").replace("—", "-").replace("−", "-")
    phone = _PHONE_PREFIX.sub("", phone).strip()
    # Drop leftover letters/punctuation but keep dial punctuation; rebuild if needed later.
    if phone and not _PHONE_OK.match(phone):
        digits = re.sub(r"\D", "", phone)
        if digits:
            # Preserve a leading + when the original had an international marker.
            if phone.lstrip().startswith("+") or phone.lstrip().startswith("00"):
                phone = "+" + digits
            else:
                phone = digits
    return phone.strip()


def normalize_recipient_phone(raw: str | None, *, required: bool = False) -> str | None:
    """Strip and validate phone for service_order_recipients.phone (VARCHAR 64)."""
    phone = sanitize_phone_input(raw)
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


def coerce_interview_phone_e164(raw: str | None) -> tuple[str | None, str | None]:
    """Normalize interview candidate phone to E.164 (UK local 07… → +44…).

    Returns (e164_or_none, error_or_none). Empty input → (None, None).
    On invalid input returns (raw_stripped, friendly_error) so the UI can show and edit it.
    """
    original = str(raw or "").strip()
    if not original:
        return None, None
    phone = sanitize_phone_input(original)
    if not phone:
        return original, (
            "That does not look like a valid phone number. "
            "Use digits with an optional + country code (7–15 digits), e.g. +447700900123."
        )
    try:
        loose = normalize_recipient_phone(phone, required=False)
    except ValueError as exc:
        return original, str(exc)
    if not loose:
        return None, None
    try:
        from app.services.telnyx_api_key import normalize_telnyx_e164

        return normalize_telnyx_e164(loose), None
    except ValueError:
        return original, "Phone number must be in E.164 format, for example +447700900123"


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
