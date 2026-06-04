"""Privacy mode helpers for WA survey templates (off = identified, on = anonymous)."""

from __future__ import annotations

import re
from typing import Any

PRIVACY_MODE_OFF = "off"
PRIVACY_MODE_ON = "on"

VARIANT_STANDARD = "standard"
VARIANT_ANONYMOUS = "anonymous"

_IDENTIFYING_PHRASES = (
    r"reference\s*number",
    r"\bref\s*#?\b",
    r"case\s*id",
    r"ticket\s*id",
    r"order\s*id",
    r"csat\s*code",
    r"tracking\s*code",
    r"customer_name",
    r"patient\s+id",
    r"account\s+number",
)
IDENTIFYING_CONTENT_RE = re.compile("|".join(_IDENTIFYING_PHRASES), re.I)


def normalize_privacy_mode(raw: Any, *, default: str = PRIVACY_MODE_OFF) -> str:
    key = str(raw or "").strip().lower()
    if key in {PRIVACY_MODE_ON, "anonymous", "true", "1", "yes", "on"}:
        return PRIVACY_MODE_ON
    if key in {PRIVACY_MODE_OFF, "standard", "identified", "false", "0", "no", "off"}:
        return PRIVACY_MODE_OFF
    return default


def privacy_mode_to_variant(privacy_mode: str) -> str:
    return VARIANT_ANONYMOUS if normalize_privacy_mode(privacy_mode) == PRIVACY_MODE_ON else VARIANT_STANDARD


def variant_to_privacy_mode(variant: str) -> str:
    return PRIVACY_MODE_ON if str(variant or "").strip().lower() == VARIANT_ANONYMOUS else PRIVACY_MODE_OFF


def resolve_row_privacy_mode(row: Any) -> str:
    explicit = getattr(row, "privacy_mode", None)
    if explicit:
        return normalize_privacy_mode(explicit)
    return variant_to_privacy_mode(getattr(row, "variant_type", None))


def resolve_mapping_privacy_mode(mapping: Any, *, template_row: Any | None = None) -> str:
    explicit = getattr(mapping, "privacy_mode", None)
    if explicit:
        return normalize_privacy_mode(explicit)
    if template_row is not None:
        return resolve_row_privacy_mode(template_row)
    if getattr(mapping, "usable_as_anonymous", False) and not getattr(mapping, "usable_as_standard", False):
        return PRIVACY_MODE_ON
    return PRIVACY_MODE_OFF


def validate_privacy_mode_content(
    *,
    privacy_mode: str,
    header: str = "",
    body: str = "",
    footer: str = "",
    example_values: list[str] | None = None,
) -> list[str]:
    """Return validation errors when anonymous privacy content includes identifying wording."""
    if normalize_privacy_mode(privacy_mode) != PRIVACY_MODE_ON:
        return []

    errors: list[str] = []
    combined = " ".join([header, body, footer, " ".join(example_values or [])]).strip()
    if not combined:
        return errors

    if "{{1}}" in combined:
        errors.append("Privacy Mode On templates must not use {{1}} (customer name variable)")

    match = IDENTIFYING_CONTENT_RE.search(combined)
    if match:
        errors.append(f"Privacy Mode On templates must not include identifying wording (“{match.group(0)}”)")

    for sample in example_values or []:
        sample_text = str(sample or "").strip()
        if not sample_text:
            continue
        if IDENTIFYING_CONTENT_RE.search(sample_text):
            errors.append("Privacy Mode On example values must not contain identifying references")
            break

    return errors
