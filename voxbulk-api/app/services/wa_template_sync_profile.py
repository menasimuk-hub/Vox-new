"""Validate connection profile for WA template sync/push."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.connection.config_resolver import (
    WhatsappRouteConfig,
    WhatsappSyncRouteError,
    resolve_whatsapp_route_for_sync,
)


def connection_profile_id_from_payload(payload: dict[str, Any] | None) -> str | None:
    pid = str((payload or {}).get("connection_profile_id") or "").strip()
    return pid or None


def resolve_sync_route_from_payload(
    db: Session,
    payload: dict[str, Any] | None,
    *,
    service_code: str = "survey",
) -> tuple[str | None, WhatsappRouteConfig | None]:
    pid = connection_profile_id_from_payload(payload)
    if not pid:
        return None, None
    try:
        route = resolve_whatsapp_route_for_sync(
            db,
            connection_profile_id=pid,
            service_code=service_code,
        )
    except WhatsappSyncRouteError as exc:
        raise ValueError(str(exc)) from exc
    return pid, route


def list_whatsapp_sync_options(db: Session, *, service_code: str = "survey") -> list[dict[str, Any]]:
    from sqlalchemy import select

    from app.models.connection_profile import CHANNEL_WHATSAPP, ConnectionProfile, ConnectionProfileService
    from app.services.connection.connection_profile_seed_service import ConnectionProfileSeedService
    from app.services.connection.constants import normalize_service_code

    ConnectionProfileSeedService.ensure_seeded(db)
    code = normalize_service_code(service_code)
    rows = list(
        db.execute(
            select(ConnectionProfile)
            .where(
                ConnectionProfile.channel == CHANNEL_WHATSAPP,
                ConnectionProfile.is_active.is_(True),
            )
            .order_by(ConnectionProfile.is_default.desc(), ConnectionProfile.name.asc())
        ).scalars()
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        svc = db.execute(
            select(ConnectionProfileService).where(
                ConnectionProfileService.profile_id == row.id,
                ConnectionProfileService.service_code == code,
            )
        ).scalar_one_or_none()
        if svc is not None and not bool(svc.enabled):
            continue
        label_bits = [str(row.name or row.id)]
        provider = str(row.provider or "").strip().lower()
        if provider == "meta":
            waba = str(row.meta_waba_id or "").strip()
            phone = str(row.meta_whatsapp_from or "").strip()
            if waba:
                label_bits.append(f"WABA {waba}")
            if phone:
                label_bits.append(phone)
        else:
            num = str(row.telnyx_number or "").strip()
            if num:
                label_bits.append(num)
        out.append(
            {
                "id": row.id,
                "name": row.name,
                "provider": provider,
                "is_default": bool(row.is_default),
                "waba_id": str(row.meta_waba_id or "").strip() or None,
                "whatsapp_from": str(row.meta_whatsapp_from or row.telnyx_number or "").strip() or None,
                "label": " · ".join(label_bits),
                "survey_enabled": True if svc is None else bool(svc.enabled),
            }
        )
    return out
