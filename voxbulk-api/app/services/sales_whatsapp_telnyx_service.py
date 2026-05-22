"""Telnyx / Meta WhatsApp template names and API components for sales automation."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

# Approved template names in Telnyx → WhatsApp → Templates (must match exactly).
TELNYX_SALES_TEMPLATE_NAMES: dict[str, str] = {
    "sales_opt_in": "voxbulk_sales_opt_in",
    "sales_offer": "voxbulk_sales_offer",
    "sales_offer_followup": "voxbulk_sales_followup",
    "sales_offer_keyword_confirm": "voxbulk_sales_keyword_confirm",
}

TELNYX_SALES_TEMPLATE_LANGUAGE = "en_US"

# Sample values for Integrations → test WhatsApp (and Telnyx portal parity checks).
TEST_TEMPLATE_VARIABLES: dict[str, str] = {
    "first_name": "Alex",
    "offer_line": "15-day free trial",
    "offer_summary": "Dental plan · £99/mo · includes calls and WhatsApp",
    "signup_url": "https://voxbulk.com/signin?promo=TEST123",
}

_LANGUAGE_FALLBACKS = ("en_US", "en_GB", "en")


def resolve_whatsapp_template_languages(db: Session | None = None) -> list[str]:
    """Language codes to try when sending Meta templates (portal may use en_GB or en_US)."""
    configured = ""
    if db is not None:
        try:
            from app.services.provider_settings import ProviderSettingsService

            cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
            if enabled and isinstance(cfg, dict):
                configured = str(cfg.get("whatsapp_template_language") or "").strip()
        except Exception:
            configured = ""
    ordered: list[str] = []
    for candidate in (configured, TELNYX_SALES_TEMPLATE_LANGUAGE, *_LANGUAGE_FALLBACKS):
        code = str(candidate or "").strip()
        if code and code not in ordered:
            ordered.append(code)
    return ordered or [TELNYX_SALES_TEMPLATE_LANGUAGE]


def template_key_for_telnyx_name(template_name: str | None) -> str | None:
    name = str(template_name or "").strip().lower()
    if not name:
        return None
    for key, meta_name in TELNYX_SALES_TEMPLATE_NAMES.items():
        if meta_name.lower() == name:
            return key
    return None


def build_test_components_for_template_name(template_name: str | None) -> list[dict[str, Any]] | None:
    """Build sample {{1}}/{{2}} parameters for known VOXBULK sales templates."""
    key = template_key_for_telnyx_name(template_name)
    if not key:
        return None
    return build_telnyx_components(key, TEST_TEMPLATE_VARIABLES)

def signup_url_query_suffix(signup_url: str) -> str:
    """Meta URL button dynamic part for https://voxbulk.com/signin?{{1}}"""
    raw = str(signup_url or "").strip()
    if not raw:
        return "promo=demo"
    parsed = urlparse(raw)
    if parsed.query:
        return parsed.query
    path = (parsed.path or "").strip("/")
    return path or "promo=demo"


def _body_params(values: list[str]) -> dict[str, Any]:
    return {
        "type": "body",
        "parameters": [{"type": "text", "text": str(v or "—")[:1024]} for v in values],
    }


def _url_button_param(index: int, suffix: str) -> dict[str, Any]:
    return {
        "type": "button",
        "sub_type": "url",
        "index": int(index),
        "parameters": [{"type": "text", "text": str(suffix or "promo=demo")[:1024]}],
    }


def build_telnyx_components(template_key: str, variables: dict[str, str]) -> list[dict[str, Any]]:
    first = str(variables.get("first_name") or "there").strip() or "there"
    offer_line = str(variables.get("offer_line") or variables.get("trial_line") or "VOXBULK offer").strip()
    offer_summary = str(variables.get("offer_summary") or variables.get("promo_name") or offer_line).strip()
    signup_suffix = signup_url_query_suffix(str(variables.get("signup_url") or ""))

    if template_key == "sales_opt_in":
        return [_body_params([first])]

    if template_key in {"sales_offer", "sales_offer_keyword_confirm"}:
        return [
            _body_params([first, offer_line, offer_summary]),
            _url_button_param(0, signup_suffix),
        ]

    if template_key == "sales_offer_followup":
        return [
            _body_params([first, offer_line]),
            _url_button_param(0, signup_suffix),
        ]

    return [_body_params([first])]


def telnyx_template_name(template_key: str) -> str | None:
    key = str(template_key or "").strip().lower()
    return TELNYX_SALES_TEMPLATE_NAMES.get(key)
