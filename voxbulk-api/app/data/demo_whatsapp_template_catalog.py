"""Platform catalog for AI Demo WhatsApp templates (WA Templates → AI Demo)."""

from __future__ import annotations

from typing import Any

from app.data.ai_demo_whatsapp_defaults import DEMO_EMAIL_SENT_BODY, DEMO_EMAIL_SENT_TEMPLATE_NAME

DEMO_WA_TEMPLATE_KEYS: tuple[str, ...] = ("demo_email_sent",)


def _body_component(body: str, examples: list[str]) -> dict[str, Any]:
    return {
        "type": "BODY",
        "text": body.strip(),
        "example": {"body_text": [examples]},
    }


def demo_spec_components(spec: dict[str, Any]) -> list[dict[str, Any]]:
    examples = [str(v) for v in (spec.get("example_values") or [])]
    return [_body_component(str(spec.get("body") or ""), examples)]


DEMO_WA_TEMPLATE_SPECS: list[dict[str, Any]] = [
    {
        "sales_template_key": "demo_email_sent",
        "telnyx_name": DEMO_EMAIL_SENT_TEMPLATE_NAME,
        "display_name": "AI demo email sent",
        "description": (
            "Sent when the demo invite email has been dispatched — "
            "asks the contact to check inbox/spam (no magic link on WhatsApp)."
        ),
        "category": "UTILITY",
        "body": DEMO_EMAIL_SENT_BODY,
        "example_values": ["James", "Acme Ltd", "hello@voxbulk.com"],
        "buttons": [],
    },
]


def demo_spec_by_key(sales_template_key: str) -> dict[str, Any] | None:
    key = str(sales_template_key or "").strip().lower()
    for spec in DEMO_WA_TEMPLATE_SPECS:
        if spec["sales_template_key"] == key:
            return spec
    return None


def demo_catalog_telnyx_names() -> set[str]:
    names: set[str] = set()
    for spec in DEMO_WA_TEMPLATE_SPECS:
        names.add(str(spec.get("telnyx_name") or "").strip().lower())
    names.add("voxbulk_demo_email_sent")  # legacy draft name
    return names
