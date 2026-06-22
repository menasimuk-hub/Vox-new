"""Platform catalog for Appointment Manager WhatsApp templates."""

from __future__ import annotations

from typing import Any

APPOINTMENT_WA_TEMPLATE_KEYS: tuple[str, ...] = (
    "appt_confirm_v1",
    "appt_confirm_v2",
    "appt_reminder_v1",
    "appt_reminder_v2",
)


def _quick_reply_buttons(labels: list[str]) -> list[dict[str, str]]:
    return [{"type": "QUICK_REPLY", "text": str(label).strip()[:25]} for label in labels if str(label).strip()]


def _body_component(body: str, examples: list[str]) -> dict[str, Any]:
    return {
        "type": "BODY",
        "text": body.strip(),
        "example": {"body_text": [examples]},
    }


def _components_from_spec(
    *,
    body: str,
    footer: str,
    examples: list[str],
    buttons: list[str] | None = None,
) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = [_body_component(body, examples)]
    built_buttons = _quick_reply_buttons(buttons or [])
    if built_buttons:
        components.append({"type": "BUTTONS", "buttons": built_buttons})
    if footer.strip():
        components.append({"type": "FOOTER", "text": footer.strip()})
    return components


APPOINTMENT_WA_TEMPLATE_SPECS: list[dict[str, Any]] = [
    {
        "sales_template_key": "appt_confirm_v1",
        "telnyx_name": "appt_confirm_v1",
        "display_name": "Appointment confirmation",
        "description": "Default confirmation with confirm / reschedule buttons",
        "category": "UTILITY",
        "body": "Hi {{1}}, this is a reminder of your {{2}} appointment on {{3}} at {{4}}. Please confirm or reschedule.",
        "footer": "Reply STOP to opt out",
        "example_values": ["Alex", "hygiene visit", "Mon 12 Jan", "10:30"],
        "buttons": ["Confirm", "Reschedule"],
    },
    {
        "sales_template_key": "appt_confirm_v2",
        "telnyx_name": "appt_confirm_v2",
        "display_name": "Friendly confirmation",
        "description": "Warm tone with single confirm button",
        "category": "UTILITY",
        "body": "Hello {{1}} 👋 Your appointment for {{2}} is booked for {{3}}. Tap below to confirm.",
        "footer": "VoxBulk appointment reminders",
        "example_values": ["Alex", "check-up", "Mon 12 Jan 10:30"],
        "buttons": ["Yes, I'll be there"],
    },
    {
        "sales_template_key": "appt_reminder_v1",
        "telnyx_name": "appt_reminder_v1",
        "display_name": "Appointment reminder",
        "description": "Reminder before visit",
        "category": "UTILITY",
        "body": "Reminder: {{1}}, you have {{2}} on {{3}} at {{4}}. Reply Y to confirm.",
        "footer": "Reply STOP to opt out",
        "example_values": ["Alex", "hygiene visit", "Mon 12 Jan", "10:30"],
        "buttons": ["Confirm", "Cancel"],
    },
    {
        "sales_template_key": "appt_reminder_v2",
        "telnyx_name": "appt_reminder_v2",
        "display_name": "Clinic reminder",
        "description": "Short clinic-style reminder",
        "category": "UTILITY",
        "body": "Hi {{1}}, we look forward to seeing you on {{3}} for {{2}}.",
        "footer": "Need to change? Tap Reschedule",
        "example_values": ["Alex", "check-up", "Mon 12 Jan"],
        "buttons": ["Reschedule"],
    },
]


def appointment_spec_by_key(key: str) -> dict[str, Any] | None:
    needle = str(key or "").strip().lower()
    for spec in APPOINTMENT_WA_TEMPLATE_SPECS:
        if str(spec.get("sales_template_key") or "").lower() == needle:
            return spec
    return None


def appointment_spec_components(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return _components_from_spec(
        body=str(spec.get("body") or ""),
        footer=str(spec.get("footer") or ""),
        examples=[str(v) for v in spec.get("example_values") or []],
        buttons=[str(b) for b in spec.get("buttons") or []],
    )


def appointment_catalog_telnyx_names() -> set[str]:
    return {str(spec.get("telnyx_name") or "").strip().lower() for spec in APPOINTMENT_WA_TEMPLATE_SPECS}
