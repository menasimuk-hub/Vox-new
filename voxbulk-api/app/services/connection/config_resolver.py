"""Resolve WhatsApp connection profile + provider config for sends and template sync."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.connection_profile import CHANNEL_WHATSAPP, PROVIDER_META, PROVIDER_TELNYX, ConnectionProfile
from app.services.connection.constants import normalize_service_code
from app.services.connection.profile_credentials import meta_config_from_profile, telnyx_config_from_profile
from app.services.connection.resolver import ConnectionProfileResolver
from app.services.meta_whatsapp_config_service import validate_meta_whatsapp_config
from app.services.provider_settings import ProviderSettingsService


class WhatsappSyncRouteError(ValueError):
    pass


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
    connection_profile_id: str | None = None,
) -> bool:
    if connection_profile_id:
        try:
            route = resolve_whatsapp_route_by_profile_id(
                db, connection_profile_id, service_code=service_code or "survey"
            )
            return route.is_meta
        except WhatsappSyncRouteError:
            return False
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


def _profile_service_enabled(db: Session, profile_id: str, service_code: str | None) -> bool:
    from app.models.connection_profile import ConnectionProfileService
    from sqlalchemy import select

    code = normalize_service_code(service_code or "survey")
    row = db.execute(
        select(ConnectionProfileService).where(
            ConnectionProfileService.profile_id == profile_id,
            ConnectionProfileService.service_code == code,
        )
    ).scalar_one_or_none()
    if row is None:
        return True
    return bool(row.enabled)


def resolve_whatsapp_route_by_profile_id(
    db: Session,
    connection_profile_id: str,
    *,
    service_code: str | None = "survey",
    require_service_enabled: bool = True,
) -> WhatsappRouteConfig:
    """Resolve WhatsApp route for an explicit connection profile (no platform fallback)."""
    pid = str(connection_profile_id or "").strip()
    if not pid:
        raise WhatsappSyncRouteError("connection_profile_id is required")
    profile = db.get(ConnectionProfile, pid)
    if profile is None:
        raise WhatsappSyncRouteError("Connection profile not found")
    if str(profile.channel or "").strip().lower() != CHANNEL_WHATSAPP:
        raise WhatsappSyncRouteError("Profile is not a WhatsApp channel profile")
    if not bool(profile.is_active):
        raise WhatsappSyncRouteError("Connection profile is inactive")
    if require_service_enabled and not _profile_service_enabled(db, pid, service_code):
        raise WhatsappSyncRouteError(f"Service {normalize_service_code(service_code or 'survey')} is disabled on this profile")

    if profile.provider == PROVIDER_META:
        try:
            cfg = validate_meta_whatsapp_config(meta_config_from_profile(profile))
        except Exception as exc:
            raise WhatsappSyncRouteError(f"Meta profile credentials invalid: {exc}") from exc
        if not (
            str(cfg.get("access_token") or "").strip()
            and str(cfg.get("phone_number_id") or "").strip()
            and str(cfg.get("waba_id") or "").strip()
        ):
            raise WhatsappSyncRouteError("Meta profile is missing access token, phone number id, or WABA id")
        return WhatsappRouteConfig(profile=profile, provider=PROVIDER_META, config=cfg)

    telnyx_cfg = telnyx_config_from_profile(profile)
    if not _telnyx_config_whatsapp_ready(telnyx_cfg):
        raise WhatsappSyncRouteError("Telnyx profile is missing API key or WhatsApp sender number")
    return WhatsappRouteConfig(profile=profile, provider=PROVIDER_TELNYX, config=telnyx_cfg)


def resolve_whatsapp_route_for_sync(
    db: Session,
    *,
    connection_profile_id: str | None = None,
    org_id: str | None = None,
    service_code: str | None = "survey",
) -> WhatsappRouteConfig:
    if connection_profile_id:
        return resolve_whatsapp_route_by_profile_id(db, connection_profile_id, service_code=service_code)
    route = resolve_whatsapp_config(db, org_id=org_id, service_code=service_code)
    if route is None:
        raise WhatsappSyncRouteError(
            "No WhatsApp connection profile or platform integration is configured for template sync"
        )
    return route


def resolve_meta_api_config(
    db: Session,
    *,
    org_id: str | None = None,
    service_code: str | None = "survey",
    connection_profile_id: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Meta Graph API credentials for template push/pull — prefer connection profile over platform integration."""
    if connection_profile_id:
        route = resolve_whatsapp_route_by_profile_id(db, connection_profile_id, service_code=service_code)
        if not route.is_meta:
            raise WhatsappSyncRouteError(f"Profile uses {route.provider}, not Meta — cannot use Meta API")
        return route.config, bool(route.profile.is_active if route.profile else True)

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
