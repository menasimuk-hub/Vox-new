"""Platform catalog for AI Interview WhatsApp templates (Platform Settings → WA Interview)."""

from __future__ import annotations

from typing import Any

from app.data.interview_booking_whatsapp_defaults import (
    INTERVIEW_BOOKING_CANCEL_BODY,
    INTERVIEW_BOOKING_CONFIRMATION_BODY,
    INTERVIEW_BOOKING_CONFIRMATION_BUTTONS,
    INTERVIEW_CANCEL_TEMPLATE_NAME,
    INTERVIEW_CONFIRMATION_TEMPLATE_NAME,
    INTERVIEW_EMAIL_SENT_BODY,
    INTERVIEW_EMAIL_SENT_TEMPLATE_NAME,
    INTERVIEW_JOB_CLOSED_BODY,
    INTERVIEW_JOB_CLOSED_TEMPLATE_NAME,
)
from app.services.sales_whatsapp_telnyx_service import (
    TELNYX_SALES_TEMPLATE_NAMES,
    legacy_telnyx_names_for_sales_key,
)

INTERVIEW_WA_TEMPLATE_KEYS: tuple[str, ...] = (
    "interview_email_sent",
    "interview_booking_confirm",
    "interview_booking_cancel",
    "interview_job_closed",
)


def _quick_reply_buttons(labels: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"type": "QUICK_REPLY", "text": str(item.get("label") or item.get("text") or "Button").strip()[:25]}
        for item in labels
        if str(item.get("label") or item.get("text") or "").strip()
    ]


def _body_component(body: str, examples: list[str]) -> dict[str, Any]:
    return {
        "type": "BODY",
        "text": body.strip(),
        "example": {"body_text": [examples]},
    }


def _components_from_spec(
    *,
    body: str,
    examples: list[str],
    buttons: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = [_body_component(body, examples)]
    built_buttons = _quick_reply_buttons(buttons or [])
    if built_buttons:
        components.append({"type": "BUTTONS", "buttons": built_buttons})
    return components


INTERVIEW_WA_TEMPLATE_SPECS: list[dict[str, Any]] = [
    {
        "sales_template_key": "interview_email_sent",
        "telnyx_name": INTERVIEW_EMAIL_SENT_TEMPLATE_NAME,
        "display_name": "Interview job email sent",
        "description": "Sent at launch when the careers email has been dispatched — asks the candidate to check inbox/spam.",
        "category": "UTILITY",
        "body": INTERVIEW_EMAIL_SENT_BODY,
        "example_values": ["James", "accountant", "menasim", "careers@voxbulk.com"],
        "buttons": [],
    },
    {
        "sales_template_key": "interview_booking_confirm",
        "telnyx_name": INTERVIEW_CONFIRMATION_TEMPLATE_NAME,
        "display_name": "Interview booking confirmation",
        "description": "Sent after the candidate books a slot — includes change/cancel quick replies.",
        "category": "UTILITY",
        "body": INTERVIEW_BOOKING_CONFIRMATION_BODY,
        "example_values": ["James", "accountant", "Sat 6 Jun 2026", "12:16 PM"],
        "buttons": list(INTERVIEW_BOOKING_CONFIRMATION_BUTTONS),
    },
    {
        "sales_template_key": "interview_booking_cancel",
        "telnyx_name": INTERVIEW_CANCEL_TEMPLATE_NAME,
        "display_name": "Interview booking cancelled",
        "description": "Sent when the candidate cancels their booked interview slot.",
        "category": "UTILITY",
        "body": INTERVIEW_BOOKING_CANCEL_BODY,
        "example_values": ["James", "accountant", "menasim", "Sat 6 Jun 2026", "12:16 PM"],
        "buttons": [],
    },
    {
        "sales_template_key": "interview_job_closed",
        "telnyx_name": INTERVIEW_JOB_CLOSED_TEMPLATE_NAME,
        "display_name": "Interview job closed",
        "description": "Sent when the employer stops the interview campaign.",
        "category": "UTILITY",
        "body": INTERVIEW_JOB_CLOSED_BODY,
        "example_values": ["James", "accountant", "menasim"],
        "buttons": [],
    },
]


def interview_spec_by_key(sales_template_key: str) -> dict[str, Any] | None:
    key = str(sales_template_key or "").strip().lower()
    for spec in INTERVIEW_WA_TEMPLATE_SPECS:
        if spec["sales_template_key"] == key:
            return spec
    return None


def interview_spec_components(spec: dict[str, Any]) -> list[dict[str, Any]]:
    examples = [str(v) for v in (spec.get("example_values") or [])]
    return _components_from_spec(
        body=str(spec.get("body") or ""),
        examples=examples,
        buttons=list(spec.get("buttons") or []),
    )


def interview_catalog_telnyx_names() -> set[str]:
    names: set[str] = set()
    for spec in INTERVIEW_WA_TEMPLATE_SPECS:
        names.add(str(spec.get("telnyx_name") or "").strip().lower())
    for key in INTERVIEW_WA_TEMPLATE_KEYS:
        mapped = TELNYX_SALES_TEMPLATE_NAMES.get(key)
        if mapped:
            names.add(str(mapped).strip().lower())
        for legacy in legacy_telnyx_names_for_sales_key(key):
            names.add(str(legacy).strip().lower())
    return names
