"""Organisation dashboard services: admin allowed modules + user visible toggles."""

from __future__ import annotations

import json
from typing import Any

DEFAULT_ENABLED_SERVICES: dict[str, bool] = {
    "interview": True,
    "survey": True,
    "recovery": False,
    "follow_up": False,
}

SERVICE_KEYS = tuple(DEFAULT_ENABLED_SERVICES.keys())


def parse_enabled_services(raw: str | None) -> dict[str, bool]:
    out = dict(DEFAULT_ENABLED_SERVICES)
    if not raw:
        return out
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return out
    if not isinstance(data, dict):
        return out
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
            "At least one dashboard service must remain enabled (interview, survey, recovery, or follow up)."
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
        "recovery": "recovery",
        "follow_up": "follow_up",
        "follow-up": "follow_up",
        "followup": "follow_up",
    }
    return mapping.get(code)


def org_service_maps(org) -> tuple[dict[str, bool], dict[str, bool], dict[str, bool]]:
    allowed = parse_allowed_services(getattr(org, "allowed_services_json", None))
    enabled = parse_enabled_services(getattr(org, "enabled_services_json", None))
    enabled = clamp_enabled_to_allowed(allowed, enabled)
    visible = effective_services(allowed, enabled)
    return allowed, enabled, visible
