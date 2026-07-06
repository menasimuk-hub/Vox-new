"""Resolve WhatsApp connection profile + provider config for sends and template sync."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.connection_profile import PROVIDER_META, PROVIDER_TELNYX, ConnectionProfile
from app.services.connection.profile_credentials import meta_config_from_profile, telnyx_config_from_profile
from app.services.connection.resolver import ConnectionProfileResolver
from app.services.meta_whatsapp_config_service import validate_meta_whatsapp_config
from app.services.provider_settings import ProviderSettingsService


@dataclass(frozen=True)
class WhatsappRouteConfig:
    profile: ConnectionProfile | None
    provider: str
    config: dict[str, Any]

    @property
    def is_meta(self) -> bool:
        return self.provider == PROVIDER_META

    @property
    def is_telnyx(self) -> bool:
        return self.provider == PROVIDER_TELNYX

    @property
    def whatsapp_from(self) -> str:
        if self.is_meta:
            return str(self.config.get("whatsapp_from") or "").strip()
        return str(
            self.config.get("whatsapp_from")
            or self.config.get("whatsapp_number")
            or self.config.get("telnyx_number")
            or ""
        ).strip()


def _platform_meta_config(db: Session) -> dict[str, Any] | None:
    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="meta_whatsapp")
    if not enabled:
        return None
    try:
        config = validate_meta_whatsapp_config(cfg or {})
    except Exception:
        return None
    if not (
        str(config.get("access_token") or "").strip()
        and str(config.get("phone_number_id") or "").strip()
        and str(config.get("waba_id") or "").strip()
    ):
        return None
    return config


def _platform_telnyx_config(db: Session) -> dict[str, Any]:
    from app.services.telnyx_messaging_service import TelnyxMessagingService

    try:
        return TelnyxMessagingService._config(db)
    except (ValueError, Exception):
        return {}


def resolve_whatsapp_config(
    db: Session,
    *,
    org_id: str | None = None,
    service_code: str | None = None,
) -> WhatsappRouteConfig | None:
    """Return active route: connection profile first, else platform integrations."""
    profile = ConnectionProfileResolver.resolve_whatsapp(
        db,
        org_id=org_id,
        service_code=service_code,
    )
    if profile is not None:
        if profile.provider == PROVIDER_META:
            return WhatsappRouteConfig(
                profile=profile,
                provider=PROVIDER_META,
                config=meta_config_from_profile(profile),
            )
        return WhatsappRouteConfig(
            profile=profile,
            provider=PROVIDER_TELNYX,
            config=telnyx_config_from_profile(profile),
        )

    meta_cfg = _platform_meta_config(db)
    if meta_cfg is not None:
        return WhatsappRouteConfig(profile=None, provider=PROVIDER_META, config=meta_cfg)

    telnyx_cfg = _platform_telnyx_config(db)
    if _telnyx_config_whatsapp_ready(telnyx_cfg):
        return WhatsappRouteConfig(profile=None, provider=PROVIDER_TELNYX, config=telnyx_cfg)
    return None


def _telnyx_config_whatsapp_ready(config: dict[str, Any]) -> bool:
    from app.services.telnyx_api_key import normalize_telnyx_api_key

    api_key = normalize_telnyx_api_key(str(config.get("api_key") or ""))
    wa_from = str(config.get("whatsapp_from") or config.get("whatsapp_number") or "").strip()
    return bool(api_key and wa_from)


def whatsapp_provider_is_meta(
    db: Session,
    *,
    org_id: str | None = None,
    service_code: str | None = None,
) -> bool:
    route = resolve_whatsapp_config(db, org_id=org_id, service_code=service_code)
    return route is not None and route.is_meta


def whatsapp_route_whatsapp_from(
    db: Session,
    *,
    org_id: str | None = None,
    service_code: str | None = None,
) -> str | None:
    route = resolve_whatsapp_config(db, org_id=org_id, service_code=service_code)
    if route is None:
        return None
    raw = route.whatsapp_from
    return raw or None


def resolve_meta_api_config(
    db: Session,
    *,
    org_id: str | None = None,
    service_code: str | None = "survey",
) -> tuple[dict[str, Any], bool]:
    """Meta Graph API credentials for template push/pull — prefer connection profile over platform integration."""
    route = resolve_whatsapp_config(db, org_id=org_id, service_code=service_code)
    if route is not None and route.is_meta:
        try:
            cfg = validate_meta_whatsapp_config(route.config)
            active = bool(route.profile.is_active) if route.profile is not None else True
            return cfg, active
        except Exception:
            pass

    platform = _platform_meta_config(db)
    if platform is not None:
        return platform, True

    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="meta_whatsapp")
    try:
        return validate_meta_whatsapp_config(cfg or {}), bool(enabled)
    except Exception:
        return {}, bool(enabled)
