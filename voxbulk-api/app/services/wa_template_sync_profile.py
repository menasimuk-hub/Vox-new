"""Validate connection profile for WA template sync/push."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.connection.config_resolver import (
    WhatsappRouteConfig,
    WhatsappSyncRouteError,
    resolve_whatsapp_route_for_sync,
)
from app.services.connection.constants import normalize_service_code


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


def summarize_for_connection_profile(
    db: Session,
    profile_id: str,
    *,
    service_code: str = "survey",
) -> dict[str, Any]:
    """Read-only live template counts for one WhatsApp connection profile (no DB mutation)."""
    from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService

    pid = str(profile_id or "").strip()
    if not pid:
        return {"ok": False, "profile_id": profile_id, "error": "Profile id is required"}

    try:
        route = resolve_whatsapp_route_for_sync(db, connection_profile_id=pid, service_code=service_code)
    except WhatsappSyncRouteError as exc:
        return {"ok": False, "profile_id": pid, "error": str(exc)}

    profile = route.profile
    provider = str(route.provider or "").strip().lower()
    waba_id = str((route.config or {}).get("waba_id") or getattr(profile, "meta_waba_id", None) or "").strip() or None
    whatsapp_from = (
        str((route.config or {}).get("whatsapp_from") or getattr(profile, "meta_whatsapp_from", None) or "")
        .strip()
        or str(getattr(profile, "telnyx_number", None) or "").strip()
        or None
    )
    label_bits = [str(getattr(profile, "name", None) or pid)]
    if provider == "meta":
        if waba_id:
            label_bits.append(f"WABA {waba_id}")
        if whatsapp_from:
            label_bits.append(whatsapp_from)
    elif whatsapp_from:
        label_bits.append(whatsapp_from)

    try:
        if route.is_meta:
            remote_all = TelnyxWhatsappTemplateSyncService.fetch_from_meta(
                db,
                connection_profile_id=pid,
                service_code=service_code,
            )
        else:
            remote_all = TelnyxWhatsappTemplateSyncService.fetch_from_telnyx(
                db,
                connection_profile_id=pid,
                service_code=service_code,
                filter_waba_id=True,
                allow_account_waba_fallback=False,
            )
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "profile_id": pid,
            "profile_label": " · ".join(label_bits),
            "provider": provider,
            "waba_id": waba_id,
            "whatsapp_from": whatsapp_from,
            "error": str(exc)[:400],
        }

    from app.services.wa_template_product_scope import filter_remote_for_service_code

    code = normalize_service_code(service_code) or "survey"
    remote = filter_remote_for_service_code(remote_all, code)
    all_summary = TelnyxWhatsappTemplateSyncService.summarize_live_remote(remote_all)
    live_summary = TelnyxWhatsappTemplateSyncService.summarize_live_remote(remote)
    remote_total = int(live_summary.get("remote_total") or 0)
    profile_total = int(all_summary.get("remote_total") or 0)
    # Live monitor: scoped total matches active hub tab; profileTotal = all templates on this WABA/account.
    return {
        "ok": True,
        "live": True,
        "profile_id": pid,
        "profile_label": " · ".join(label_bits),
        "provider": provider,
        "waba_id": waba_id,
        "whatsapp_from": whatsapp_from,
        "service_code": code,
        "summary": {
            "utility": int(live_summary.get("utility") or 0),
            "marketing": int(live_summary.get("marketing") or 0),
            "approved": int(live_summary.get("approved") or 0),
            "pending": int(live_summary.get("pending") or 0),
            "rejected": int(live_summary.get("rejected") or 0),
            "localOnly": 0,
            "total": remote_total,
            "profileTotal": profile_total,
            "scopedTotal": remote_total,
        },
    }


def summarize_connection_profiles_batch(
    db: Session,
    profile_ids: list[str],
    *,
    service_code: str = "survey",
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for pid in profile_ids:
        pid = str(pid or "").strip()
        if not pid:
            continue
        items.append(summarize_for_connection_profile(db, pid, service_code=service_code))
    return items
