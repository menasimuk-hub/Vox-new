"""Organisation-level dashboard service toggles (interview, survey, recovery, follow-up)."""

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


def serialize_enabled_services(services: dict[str, Any] | None) -> str:
    base = parse_enabled_services(None)
    if isinstance(services, dict):
        for key in SERVICE_KEYS:
            if key in services:
                base[key] = bool(services[key])
    return json.dumps(base, ensure_ascii=False)


def any_service_enabled(services: dict[str, bool]) -> bool:
    return any(bool(services.get(k)) for k in SERVICE_KEYS)
