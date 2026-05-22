"""Telnyx / Meta WhatsApp template names and API components for sales automation."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

# Approved template names in Telnyx → WhatsApp → Templates (must match exactly).
TELNYX_SALES_TEMPLATE_NAMES: dict[str, str] = {
    "sales_opt_in": "voxbulk_sales_opt_in",
    "sales_offer": "voxbulk_sales_offer",
    "sales_offer_followup": "voxbulk_sales_followup",
    "sales_offer_keyword_confirm": "voxbulk_sales_keyword_confirm",
}

TELNYX_SALES_TEMPLATE_LANGUAGE = "en_GB"


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
        "index": str(index),
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
