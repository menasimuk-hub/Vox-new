"""Unified catalogue of org-visible integrations.

This is the single source of truth for the redesigned dashboard Integrations
page. It joins:

- admin platform config (`provider_configs.is_enabled` + `visible_to_orgs`)
- per-org connection state (`scheduling_config_json` / `hubspot_config_json`)
- a hard-coded provider registry (label, description, group, action URLs)

Wave 1 surfaces six providers split across two groups:

- ``booking``: Calendly, Cal.com, Google Calendar, HubSpot Meetings, Microsoft Calendar
- ``crm``: HubSpot

A provider is only included in ``list_integrations_for_org`` when both
``is_enabled`` and ``visible_to_orgs`` are true on its admin row (with
sensible fallbacks for the legacy single-toggle world).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.provider_config import ProviderConfig


BOOKING_GROUP = "booking"
CRM_GROUP = "crm"


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    group: str  # "booking" | "crm"
    admin_provider: str  # the provider_configs.provider row that gates visibility
    label: str
    short_description: str
    icon_slug: str
    docs_url: str | None = None


PROVIDER_REGISTRY: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        key="calendly",
        group=BOOKING_GROUP,
        admin_provider="calendly",
        label="Calendly",
        short_description="Send shortlisted candidates a one-time Calendly booking link.",
        icon_slug="calendly",
    ),
    ProviderSpec(
        key="cal_com",
        group=BOOKING_GROUP,
        admin_provider="cal_com",
        label="Cal.com",
        short_description="Self-hosted-friendly scheduling — pick an event type and share it with candidates.",
        icon_slug="cal_com",
    ),
    ProviderSpec(
        key="google_calendar",
        group=BOOKING_GROUP,
        admin_provider="google_calendar",
        label="Google Calendar",
        short_description="Use a Google Appointment Schedule page as the candidate-facing booking flow.",
        icon_slug="google_calendar",
    ),
    ProviderSpec(
        key="microsoft_calendar",
        group=BOOKING_GROUP,
        admin_provider="microsoft_calendar",
        label="Microsoft 365 Calendar",
        short_description="Connect Outlook 365 / Microsoft Bookings and share your booking page with candidates.",
        icon_slug="microsoft_calendar",
    ),
    ProviderSpec(
        key="hubspot_meetings",
        group=BOOKING_GROUP,
        admin_provider="hubspot",
        label="HubSpot Meetings",
        short_description="Reuse your HubSpot meeting links (requires HubSpot CRM connected).",
        icon_slug="hubspot",
    ),
    ProviderSpec(
        key="zoho_bookings",
        group=BOOKING_GROUP,
        admin_provider="zoho_bookings",
        label="Zoho Bookings",
        short_description="Share a Zoho Bookings page with candidates (requires Zoho CRM connected).",
        icon_slug="zoho",
    ),
    ProviderSpec(
        key="hubspot",
        group=CRM_GROUP,
        admin_provider="hubspot",
        label="HubSpot CRM",
        short_description="Import contacts, push interview shortlists, and write survey results back to HubSpot.",
        icon_slug="hubspot",
    ),
    ProviderSpec(
        key="pipedrive",
        group=CRM_GROUP,
        admin_provider="pipedrive",
        label="Pipedrive",
        short_description="Push interview shortlists and candidate updates to Pipedrive contacts and deals.",
        icon_slug="pipedrive",
    ),
    ProviderSpec(
        key="zoho_crm",
        group=CRM_GROUP,
        admin_provider="zoho_crm",
        label="Zoho CRM",
        short_description="Push interview shortlists and candidate updates to Zoho CRM contacts and deals.",
        icon_slug="zoho",
    ),
)


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _admin_rows(db: Session) -> dict[str, ProviderConfig]:
    rows = db.execute(
        select(ProviderConfig).where(
            ProviderConfig.scope == "platform",
            ProviderConfig.org_id.is_(None),
        )
    ).scalars().all()
    return {row.provider: row for row in rows}


def _is_provider_visible(spec: ProviderSpec, admin_row: ProviderConfig | None) -> bool:
    if admin_row is None:
        return False
    if not bool(admin_row.is_enabled):
        return False
    return bool(getattr(admin_row, "visible_to_orgs", False))


def _booking_connection_view(spec: ProviderSpec, org: Organisation, db: Session) -> dict[str, Any]:
    from app.services.booking_providers import connected_account_display, provider_label

    cfg = _loads(getattr(org, "scheduling_config_json", None))
    connected_provider = str(cfg.get("provider") or "").strip().lower()
    is_active = connected_provider == spec.key

    base: dict[str, Any] = {
        "connected": False,
        "connected_account": None,
        "connected_at": None,
        "extra": {},
    }
    if not is_active:
        return base

    if spec.key == "calendly":
        connected = bool(str(cfg.get("access_token") or "").strip())
    elif spec.key == "hubspot_meetings":
        connected = bool(str(cfg.get("meeting_link_url") or "").strip())
    elif spec.key == "zoho_bookings":
        connected = bool(str(cfg.get("service_url") or "").strip())
    elif spec.key in {"cal_com", "google_calendar", "microsoft_calendar"}:
        connected = bool(str(cfg.get("access_token") or "").strip())
    else:
        connected = bool(connected_provider)

    last_check = cfg.get("last_check") if isinstance(cfg.get("last_check"), dict) else None

    extra = {
        "provider_label": provider_label(spec.key),
        "event_type_url": (
            cfg.get("event_type_url")
            or cfg.get("schedule_url")
            or cfg.get("meeting_link_url")
            or cfg.get("event_type_uri")
        ),
        "schedule_name": cfg.get("schedule_name") or cfg.get("meeting_link_name") or cfg.get("event_type_slug"),
        "expires_at": cfg.get("expires_at"),
    }

    return {
        "connected": connected,
        "connected_account": connected_account_display(cfg),
        "connected_at": cfg.get("connected_at"),
        "last_check": last_check,
        "extra": extra,
    }


def _crm_connection_view(spec: ProviderSpec, org: Organisation, db: Session) -> dict[str, Any]:
    from app.services.crm_providers import CRM_CONFIG_COLUMNS

    column = CRM_CONFIG_COLUMNS.get(spec.key)
    if not column:
        return {"connected": False, "connected_account": None, "connected_at": None, "extra": {}}

    cfg = _loads(getattr(org, column, None))
    has_token = bool(str(cfg.get("access_token") or "").strip())
    last_check = cfg.get("last_check") if isinstance(cfg.get("last_check"), dict) else None
    account_name = str(cfg.get("account_name") or "").strip() or None
    hub_domain = str(cfg.get("hub_domain") or cfg.get("company_domain") or "").strip() or None

    extra: dict[str, Any] = {
        "auth_mode": cfg.get("auth_mode"),
        "auto_sync_shortlist": cfg.get("auto_sync_shortlist", True) is not False,
        "auto_sync_scheduling_send": cfg.get("auto_sync_scheduling_send", True) is not False,
    }
    if spec.key == "hubspot":
        extra.update({"hub_domain": hub_domain, "hub_id": cfg.get("hub_id")})
    elif spec.key == "pipedrive":
        extra.update({"company_domain": cfg.get("company_domain"), "company_name": cfg.get("company_name")})
    elif spec.key == "zoho_crm":
        extra.update({"data_center": cfg.get("data_center"), "api_domain": cfg.get("api_domain")})

    return {
        "connected": has_token,
        "connected_account": account_name or hub_domain,
        "connected_at": cfg.get("connected_at"),
        "last_check": last_check,
        "extra": extra,
    }


def _provider_actions(spec: ProviderSpec) -> dict[str, str]:
    base = "/service-orders"
    actions = {
        "test_url": f"{base}/integrations/{spec.key}/test",
        "disconnect_url": f"{base}/integrations/{spec.key}/disconnect",
    }
    if spec.group == BOOKING_GROUP:
        if spec.key == "calendly":
            actions["connect_url"] = f"{base}/scheduling/oauth/calendly/start"
        elif spec.key == "cal_com":
            actions["connect_url"] = f"{base}/scheduling/oauth/cal-com/start"
        elif spec.key == "google_calendar":
            actions["connect_url"] = f"{base}/scheduling/oauth/google-calendar/start"
        elif spec.key == "microsoft_calendar":
            actions["connect_url"] = f"{base}/scheduling/oauth/microsoft-calendar/start"
        elif spec.key == "hubspot_meetings":
            # Connects via HubSpot meeting-link picker, not a fresh OAuth.
            actions["connect_url"] = f"{base}/scheduling/hubspot/meeting-links"
        elif spec.key == "zoho_bookings":
            actions["connect_url"] = f"{base}/scheduling/zoho/booking-services"
    elif spec.group == CRM_GROUP:
        if spec.key == "hubspot":
            actions["connect_url"] = f"{base}/hubspot/oauth/start"
            actions["connect_token_url"] = f"{base}/hubspot/connect-token"
        elif spec.key == "pipedrive":
            actions["connect_url"] = f"{base}/pipedrive/oauth/start"
        elif spec.key == "zoho_crm":
            actions["connect_url"] = f"{base}/zoho-crm/oauth/start"
    return actions


def _platform_ready_for(spec: ProviderSpec, db: Session) -> bool:
    if spec.group == BOOKING_GROUP:
        from app.services.scheduling_connection_service import platform_oauth_configured

        if spec.key == "hubspot_meetings":
            from app.services.hubspot_connection_service import platform_oauth_configured as hs_ready

            return bool(hs_ready(db))
        if spec.key == "zoho_bookings":
            from app.services.zoho_crm_connection_service import platform_oauth_configured as zoho_ready

            return bool(zoho_ready(db))
        if spec.key == "microsoft_calendar":
            from app.services.microsoft_calendar_service import platform_oauth_configured as ms_ready

            return bool(ms_ready(db))
        return bool(platform_oauth_configured(db, spec.key))

    if spec.key == "hubspot":
        from app.services.hubspot_connection_service import platform_oauth_configured as hs_ready

        return bool(hs_ready(db))
    if spec.key == "pipedrive":
        from app.services.pipedrive_connection_service import platform_oauth_configured as pd_ready

        return bool(pd_ready(db))
    if spec.key == "zoho_crm":
        from app.services.zoho_crm_connection_service import platform_oauth_configured as zoho_ready

        return bool(zoho_ready(db))
    return False


def _iso_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def list_integrations_for_org(db: Session, org_id: str) -> dict[str, list[dict[str, Any]]]:
    """Return the integrations the org can see, grouped by category."""
    from app.services.crm_connection_service import active_crm_provider, crm_provider_label
    from app.services.crm_providers import CRM_DEPENDENT_BOOKING

    org = db.get(Organisation, org_id)
    admin_rows = _admin_rows(db)

    booking: list[dict[str, Any]] = []
    crm: list[dict[str, Any]] = []

    active_booking_provider: str | None = None
    if org is not None:
        active_booking_provider = str(
            _loads(getattr(org, "scheduling_config_json", None)).get("provider") or ""
        ).strip().lower() or None

    active_crm = active_crm_provider(db, org_id) if org is not None else None

    for spec in PROVIDER_REGISTRY:
        admin_row = admin_rows.get(spec.admin_provider)
        visible = _is_provider_visible(spec, admin_row)
        if not visible:
            continue
        platform_ready = _platform_ready_for(spec, db)
        connection_view = (
            _booking_connection_view(spec, org, db) if (spec.group == BOOKING_GROUP and org is not None)
            else _crm_connection_view(spec, org, db) if (spec.group == CRM_GROUP and org is not None)
            else {"connected": False, "connected_account": None, "connected_at": None, "extra": {}}
        )

        another_booking_active = (
            spec.group == BOOKING_GROUP
            and active_booking_provider is not None
            and active_booking_provider != spec.key
        )
        parent_crm = CRM_DEPENDENT_BOOKING.get(spec.key)
        missing_parent_crm = (
            spec.group == BOOKING_GROUP
            and parent_crm is not None
            and active_crm != parent_crm
            and not connection_view.get("connected")
        )
        another_crm_active = (
            spec.group == CRM_GROUP
            and active_crm is not None
            and active_crm != spec.key
            and not connection_view.get("connected")
        )

        blocked_reason: str | None = None
        if another_booking_active and not connection_view.get("connected"):
            blocked_reason = "Another booking provider is currently active."
        elif missing_parent_crm:
            parent_label = crm_provider_label(parent_crm) or parent_crm.replace("_", " ").title()
            blocked_reason = f"Connect {parent_label} first."
        elif another_crm_active:
            current_label = crm_provider_label(active_crm) or active_crm.replace("_", " ").title()
            blocked_reason = f"Disconnect {current_label} first to connect this CRM."

        last_check = connection_view.get("last_check") or {}
        last_check_ok = last_check.get("ok") if isinstance(last_check, dict) else None
        last_check_at = last_check.get("checked_at") if isinstance(last_check, dict) else None

        entry: dict[str, Any] = {
            "key": spec.key,
            "group": spec.group,
            "label": spec.label,
            "short_description": spec.short_description,
            "icon_slug": spec.icon_slug,
            "platform_ready": platform_ready,
            "visible_to_orgs": True,
            "connected": bool(connection_view.get("connected")),
            "connected_account": connection_view.get("connected_account"),
            "connected_at": _iso_or_none(connection_view.get("connected_at")),
            "last_check_ok": last_check_ok,
            "last_check_at": _iso_or_none(last_check_at),
            "blocked_reason": blocked_reason,
            "actions": _provider_actions(spec),
            "extra": connection_view.get("extra") or {},
        }
        if spec.group == BOOKING_GROUP:
            booking.append(entry)
        else:
            crm.append(entry)

    return {
        "booking": booking,
        "crm": crm,
        "active_booking_provider": active_booking_provider if any(b["connected"] for b in booking) else None,
        "active_crm_provider": active_crm if any(c["connected"] for c in crm) else None,
    }


def resolve_provider_spec(key: str) -> ProviderSpec | None:
    needle = str(key or "").strip().lower()
    for spec in PROVIDER_REGISTRY:
        if spec.key == needle:
            return spec
    return None
