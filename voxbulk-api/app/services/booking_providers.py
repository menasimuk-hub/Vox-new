"""Shared booking provider registry for org-level human interview scheduling."""

from __future__ import annotations

BOOKING_PROVIDERS: tuple[str, ...] = (
    "calendly",
    "hubspot_meetings",
    "google_calendar",
    "cal_com",
)

PROVIDER_LABELS: dict[str, str] = {
    "calendly": "Calendly",
    "hubspot_meetings": "HubSpot Meetings",
    "google_calendar": "Google Calendar",
    "cal_com": "Cal.com",
    "cronofy": "Cronofy",
}

LEGACY_UNSUPPORTED_PROVIDERS: frozenset[str] = frozenset({"cronofy"})


def provider_label(provider: str | None) -> str | None:
    key = str(provider or "").strip().lower()
    if not key:
        return None
    return PROVIDER_LABELS.get(key, key.replace("_", " ").title())


def is_active_booking_provider(provider: str | None) -> bool:
    return str(provider or "").strip().lower() in BOOKING_PROVIDERS


def connected_account_display(cfg: dict) -> str | None:
    owner = str(cfg.get("owner_name") or cfg.get("account_name") or "").strip()
    email = str(cfg.get("owner_email") or cfg.get("email") or "").strip()
    meeting_name = str(cfg.get("meeting_link_name") or cfg.get("schedule_name") or "").strip()
    if owner and email and owner.lower() != email.lower():
        return f"{owner} · {email}"
    if owner:
        return owner
    if email:
        return email
    if meeting_name:
        return meeting_name
    slug = str(cfg.get("event_type_slug") or cfg.get("username") or "").strip()
    if slug:
        return slug
    return None
