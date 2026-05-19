from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.services.telnyx_api_key import normalize_telnyx_e164

# Shown in assistant instructions and {{country}} / {{country_code}} headers.
_REGION_DIAL: dict[str, str] = {
    "GB": "+44",
    "US": "+1",
    "CA": "+1",
    "IE": "+353",
    "AU": "+61",
    "DE": "+49",
    "FR": "+33",
    "ES": "+34",
    "IT": "+39",
    "NL": "+31",
    "AE": "+971",
    "SA": "+966",
    "IN": "+91",
}

_REGION_NAME: dict[str, str] = {
    "GB": "United Kingdom",
    "US": "United States",
    "CA": "Canada",
    "IE": "Ireland",
    "AU": "Australia",
    "DE": "Germany",
    "FR": "France",
    "ES": "Spain",
    "IT": "Italy",
    "NL": "Netherlands",
    "AE": "United Arab Emirates",
    "SA": "Saudi Arabia",
    "IN": "India",
}

_LOCALE_REGION: dict[str, str] = {
    "en-gb": "GB",
    "en-us": "US",
    "en-ca": "CA",
    "en-au": "AU",
    "en-ie": "IE",
}

_TZ_REGION: dict[str, str] = {
    "europe/london": "GB",
    "europe/dublin": "IE",
    "europe/paris": "FR",
    "europe/berlin": "DE",
    "europe/amsterdam": "NL",
    "europe/madrid": "ES",
    "europe/rome": "IT",
    "america/new_york": "US",
    "america/chicago": "US",
    "america/denver": "US",
    "america/los_angeles": "US",
    "america/toronto": "CA",
    "australia/sydney": "AU",
    "asia/dubai": "AE",
    "asia/riyadh": "SA",
    "asia/kolkata": "IN",
}

_TELNYX_VARIABLES_BLOCK = """
## Website form data (Telnyx dynamic variables)
The visitor completed the Talk to us form before this call. SIP headers supply these variables — use them immediately; do not ask them to repeat name, company, or email unless confirming.

- Name: {{contact_name}}
- Company: {{company_name}}
- Email: {{email}}
- Phone (normalized): {{phone}}
- Phone (as entered): {{phone_raw}}
- Country: {{country}}
- Country dial code: {{country_code}}
- Browser timezone: {{timezone}}
- Browser locale: {{locale}}

Begin within a few seconds — short opening (under 12 words), greet {{contact_name}} by first name, then say once: "This call is recorded for quality — privacy details are on voxbulk.com." Phone from the form: if {{phone}} is set, read it back once and ask "Is that still correct?" — do not ask again if they say yes. If {{phone}} is empty, ask once for their best callback number. Only re-confirm if they give a different number than {{phone_raw}}.
""".strip()


@dataclass
class LeadLocationHints:
    region: str
    country: str
    country_code: str
    timezone: str | None = None
    locale: str | None = None


_TELNYX_BLOCK_MARKER = "## Website form data (Telnyx dynamic variables)"


def ensure_telnyx_variables_block(instructions: str) -> str:
    """Append or replace the Telnyx form-variables block so saves pick up rule changes."""
    text = str(instructions or "").strip()
    if _TELNYX_BLOCK_MARKER in text:
        text = text.split(_TELNYX_BLOCK_MARKER)[0].rstrip()
    if not text:
        return _TELNYX_VARIABLES_BLOCK
    return f"{text}\n\n{_TELNYX_VARIABLES_BLOCK}"


def _region_from_phone(phone: str) -> str | None:
    clean = str(phone or "").strip()
    if not clean.startswith("+"):
        return None
    digits = re.sub(r"\D", "", clean)
    if digits.startswith("44"):
        return "GB"
    if digits.startswith("1") and len(digits) >= 11:
        return "US"
    if digits.startswith("353"):
        return "IE"
    if digits.startswith("61"):
        return "AU"
    if digits.startswith("971"):
        return "AE"
    if digits.startswith("966"):
        return "SA"
    if digits.startswith("91"):
        return "IN"
    return None


def resolve_lead_location(
    *,
    phone: str | None = None,
    client_timezone: str | None = None,
    client_locale: str | None = None,
    client_country: str | None = None,
    default_region: str = "GB",
) -> LeadLocationHints:
    region = str(client_country or "").strip().upper()[:2] or None
    if not region:
        region = _region_from_phone(str(phone or ""))
    tz = str(client_timezone or "").strip() or None
    loc = str(client_locale or "").strip().lower() or None
    if not region and loc:
        region = _LOCALE_REGION.get(loc) or _LOCALE_REGION.get(loc.split("-")[0] + "-" + loc.split("-")[-1] if "-" in loc else "")
    if not region and tz:
        region = _TZ_REGION.get(tz.lower())
    if not region:
        region = default_region.upper()[:2] or "GB"
    dial = _REGION_DIAL.get(region, "+44")
    country = _REGION_NAME.get(region, region)
    return LeadLocationHints(region=region, country=country, country_code=dial, timezone=tz, locale=loc)


def normalize_lead_phone(phone: str | None, location: LeadLocationHints) -> tuple[str | None, str]:
    raw = str(phone or "").strip()
    if not raw:
        return None, ""
    if raw.startswith("+"):
        try:
            return normalize_telnyx_e164(raw), raw
        except Exception:
            return raw, raw
    local = raw.replace(" ", "")
    if local.startswith("0") and location.region == "GB":
        try:
            return normalize_telnyx_e164(local), raw
        except Exception:
            pass
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None, raw
    dial_digits = re.sub(r"\D", "", location.country_code)
    if local.startswith("0"):
        normalized = f"+{dial_digits}{digits[1:]}"
    elif digits.startswith(dial_digits):
        normalized = f"+{digits}"
    else:
        normalized = f"+{dial_digits}{digits}"
    try:
        return normalize_telnyx_e164(normalized), raw
    except Exception:
        return normalized, raw


def build_telnyx_custom_headers(
    *,
    call_id: str,
    contact_name: str,
    company_name: str,
    email: str,
    phone_e164: str | None,
    phone_raw: str,
    location: LeadLocationHints,
) -> list[dict[str, str]]:
    headers: list[dict[str, str]] = [
        {"name": "X-Lead-Call-Id", "value": call_id},
        {"name": "X-Contact-Name", "value": contact_name},
        {"name": "X-Company-Name", "value": company_name},
        {"name": "X-Email", "value": email},
        {"name": "X-Phone", "value": phone_e164 or phone_raw or ""},
        {"name": "X-Phone-Raw", "value": phone_raw or ""},
        {"name": "X-Country", "value": location.country},
        {"name": "X-Country-Code", "value": location.country_code},
    ]
    if location.timezone:
        headers.append({"name": "X-Timezone", "value": location.timezone})
    if location.locale:
        headers.append({"name": "X-Locale", "value": location.locale})
    return [row for row in headers if str(row.get("value") or "").strip()]


def build_lead_context_message(
    *,
    contact_name: str,
    company_name: str,
    email: str,
    phone_e164: str | None,
    phone_raw: str,
    location: LeadLocationHints,
) -> str:
    phone_line = phone_e164 or phone_raw or "(not provided)"
    return (
        "Website form submitted before this call. "
        f"Name: {contact_name}. Company: {company_name}. Email: {email}. "
        f"Phone on file: {phone_line}. Country: {location.country} ({location.country_code}). "
        f"Timezone: {location.timezone or 'unknown'}. "
        "Greet them by first name. Phone is on file — confirm it once only if needed."
    )


def enrich_lead_context_text(
    base_context: str,
    *,
    location: LeadLocationHints,
    phone_e164: str | None,
    phone_raw: str,
) -> str:
    lines = [base_context.strip(), "", "## Location and phone", f"- Country: {location.country} ({location.country_code})"]
    if location.timezone:
        lines.append(f"- Browser timezone: {location.timezone}")
    if location.locale:
        lines.append(f"- Browser locale: {location.locale}")
    if phone_e164:
        lines.append(f"- Phone (E.164): {phone_e164}")
    if phone_raw and phone_raw != phone_e164:
        lines.append(f"- Phone (as entered): {phone_raw}")
    lines.append(
        "- Phone is on file: read it back once and ask if it is still correct. Do not repeat unless they correct it."
    )
    return "\n".join(lines)
