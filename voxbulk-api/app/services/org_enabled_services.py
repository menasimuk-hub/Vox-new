"""Organisation dashboard services: admin allowed modules + user visible toggles."""

from __future__ import annotations

import json
from typing import Any

DEFAULT_ENABLED_SERVICES: dict[str, bool] = {
    "interview": True,
    "survey": True,
    "customer_feedback": False,
    "recovery": False,
    "follow_up": False,
    "campaigns": False,
    "appointments": False,
}

SERVICE_KEYS = tuple(DEFAULT_ENABLED_SERVICES.keys())

SERVICE_LABELS: dict[str, str] = {
    "interview": "Interviews",
    "survey": "Surveys",
    "customer_feedback": "Customer feedback",
    "appointments": "Appointments",
    "recovery": "Recovery",
    "follow_up": "Follow up",
    "campaigns": "Broadcast campaigns",
}

SERVICE_ADMIN_ICONS: dict[str, str] = {
    "interview": "ti-phone",
    "survey": "ti-clipboard",
    "customer_feedback": "ti-message-circle",
    "appointments": "ti-calendar",
    "recovery": "ti-heart",
    "follow_up": "ti-bell",
    "campaigns": "ti-megaphone",
}

# Brand asset keys under voxbulk-api/logos/ (served at /public/brand/{key})
DASHBOARD_SERVICE_ICONS: dict[str, str] = {
    "interview": "icon-black",
    "survey": "icon-black",
    "customer_feedback": "icon-black",
    "recovery": "icon-black",
    "follow_up": "icon-black",
    "campaigns": "icon-dark",
    "appointments": "icon-black",
}


def dashboard_service_icon_urls(*, api_origin: str | None = None) -> dict[str, str]:
    from app.services.brand_assets import api_public_origin, public_brand_url

    origin = api_origin or api_public_origin()
    return {
        key: public_brand_url(origin, asset_key)
        for key, asset_key in DASHBOARD_SERVICE_ICONS.items()
    }


def parse_enabled_services(raw: str | None, *, platform_default: dict[str, bool] | None = None) -> dict[str, bool]:
    base = dict(platform_default) if platform_default is not None else dict(DEFAULT_ENABLED_SERVICES)
    if not raw:
        return base
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return base
    if not isinstance(data, dict):
        return base
    out = dict(base)
    for key in SERVICE_KEYS:
        if key in data:
            out[key] = bool(data[key])
    return out


parse_allowed_services = parse_enabled_services


def serialize_enabled_services(services: dict[str, Any] | None) -> str:
    base = parse_enabled_services(None)
    if isinstance(services, dict):
        for key in SERVICE_KEYS:
            if key in services:
                base[key] = bool(services[key])
    return json.dumps(base, ensure_ascii=False)


serialize_allowed_services = serialize_enabled_services


def any_service_enabled(services: dict[str, bool]) -> bool:
    return any(bool(services.get(k)) for k in SERVICE_KEYS)


class AtLeastOneServiceRequiredError(ValueError):
    """Raised when a patch would disable every dashboard module."""


class ServiceNotAllowedError(ValueError):
    """Raised when user tries to enable a module not allowed by admin."""


def validate_at_least_one_enabled(services: dict[str, bool]) -> None:
    if not any_service_enabled(services):
        raise AtLeastOneServiceRequiredError(
            "At least one dashboard service must remain enabled (interview, survey, customer feedback, recovery, follow up, or campaigns)."
        )


def merge_enabled_services(current: dict[str, bool], patch: dict[str, Any] | None) -> dict[str, bool]:
    merged = dict(current)
    if isinstance(patch, dict):
        for key in SERVICE_KEYS:
            if key in patch:
                merged[key] = bool(patch[key])
    validate_at_least_one_enabled(merged)
    return merged


def clamp_enabled_to_allowed(
    allowed: dict[str, bool],
    enabled: dict[str, bool],
) -> dict[str, bool]:
    out = dict(enabled)
    for key in SERVICE_KEYS:
        if not allowed.get(key):
            out[key] = False
    return out


def effective_services(allowed: dict[str, bool], enabled: dict[str, bool]) -> dict[str, bool]:
    return {key: bool(allowed.get(key)) and bool(enabled.get(key)) for key in SERVICE_KEYS}


def merge_user_enabled_services(
    allowed: dict[str, bool],
    current_enabled: dict[str, bool],
    patch: dict[str, Any] | None,
) -> dict[str, bool]:
    merged = dict(current_enabled)
    if isinstance(patch, dict):
        for key in SERVICE_KEYS:
            if key not in patch:
                continue
            value = bool(patch[key])
            if value and not allowed.get(key):
                raise ServiceNotAllowedError(
                    f"Service '{key}' is not available for this organisation. Contact your account manager."
                )
            merged[key] = value
    merged = clamp_enabled_to_allowed(allowed, merged)
    if not any_service_enabled(effective_services(allowed, merged)):
        raise AtLeastOneServiceRequiredError(
            "At least one available service must stay visible on your dashboard."
        )
    return merged


def apply_admin_org_service_grants(
    current_enabled: dict[str, bool],
    grants: dict[str, Any],
) -> tuple[dict[str, bool], dict[str, bool]]:
    """Replace org allowed grants from admin UI (full matrix). Clamp user enabled to match."""
    allowed = {key: bool(grants.get(key)) for key in SERVICE_KEYS}
    validate_at_least_one_enabled(allowed)
    enabled = clamp_enabled_to_allowed(allowed, current_enabled)
    if not any_service_enabled(effective_services(allowed, enabled)):
        enabled = {key: bool(allowed.get(key)) for key in SERVICE_KEYS}
    return allowed, enabled


def merge_admin_allowed_services(
    current_allowed: dict[str, bool],
    current_enabled: dict[str, bool],
    patch: dict[str, Any] | None,
) -> tuple[dict[str, bool], dict[str, bool]]:
    allowed = merge_enabled_services(current_allowed, patch)
    enabled = clamp_enabled_to_allowed(allowed, current_enabled)
    if not any_service_enabled(effective_services(allowed, enabled)):
        enabled = dict(allowed)
    validate_at_least_one_enabled(allowed)
    return allowed, enabled


def is_service_enabled(services: dict[str, bool], service_key: str) -> bool:
    return bool(services.get(service_key))


def service_code_to_enabled_key(service_code: str) -> str | None:
    code = str(service_code or "").strip().lower()
    mapping = {
        "interview": "interview",
        "interviews": "interview",
        "survey": "survey",
        "surveys": "survey",
        "customer_feedback": "customer_feedback",
        "feedback": "customer_feedback",
        "recovery": "recovery",
        "follow_up": "follow_up",
        "follow-up": "follow_up",
        "followup": "follow_up",
        "campaigns": "campaigns",
        "appointments": "appointments",
        "appointment": "appointments",
        "appointment_manager": "appointments",
    }
    return mapping.get(code)


def org_service_maps(org, db=None) -> tuple[dict[str, bool], dict[str, bool], dict[str, bool]]:
    platform_default = None
    if db is not None:
        from app.services.platform_services_settings_service import get_platform_default_allowed

        platform_default = get_platform_default_allowed(db)
    raw_allowed = getattr(org, "allowed_services_json", None)
    uses_platform_default = raw_allowed is None or not str(raw_allowed).strip()
    allowed = parse_allowed_services(
        None if uses_platform_default else raw_allowed,
        platform_default=platform_default,
    )
    enabled = parse_enabled_services(getattr(org, "enabled_services_json", None))
    enabled = clamp_enabled_to_allowed(allowed, enabled)
    visible = effective_services(allowed, enabled)
    return allowed, enabled, visible


def org_uses_platform_default_allowed(org) -> bool:
    raw = getattr(org, "allowed_services_json", None)
    return raw is None or not str(raw).strip()


def customer_service_status(*, allowed: bool, enabled: bool, visible: bool) -> str:
    if not allowed:
        return "Not granted"
    if visible:
        return "Visible in app"
    if enabled:
        return "Visible in app"
    return "Available in Settings"


def build_service_breakdown(
    allowed: dict[str, bool],
    enabled: dict[str, bool],
    visible: dict[str, bool],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in SERVICE_KEYS:
        a = bool(allowed.get(key))
        e = bool(enabled.get(key))
        v = bool(visible.get(key))
        rows.append(
            {
                "key": key,
                "label": SERVICE_LABELS.get(key, key.replace("_", " ").title()),
                "icon": SERVICE_ADMIN_ICONS.get(key, "ti-circle-dot"),
                "allowed": a,
                "enabled": e,
                "visible": v,
                "customer_status": customer_service_status(allowed=a, enabled=e, visible=v),
            }
        )
    return rows
