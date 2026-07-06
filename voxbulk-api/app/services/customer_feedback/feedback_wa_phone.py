"""Resolve Customer Feedback WhatsApp number from connection profile or platform settings."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackWaSender
from app.services.connection.config_resolver import whatsapp_route_whatsapp_from
from app.services.connection.constants import SERVICE_CUSTOMER_FEEDBACK
from app.services.market_zone import country_to_zone

PLACEHOLDER_WA_E164 = "+447700900000"


def get_telnyx_whatsapp_from_e164(db: Session, *, org_id: str | None = None) -> str | None:
    """Resolved WhatsApp from-number for Customer Feedback (profile or platform Telnyx)."""
    phone = whatsapp_route_whatsapp_from(
        db,
        org_id=org_id,
        service_code=SERVICE_CUSTOMER_FEEDBACK,
    )
    if phone:
        return phone

    from app.services.provider_settings import ProviderSettingsService
    from app.services.telnyx_api_key import normalize_telnyx_e164

    cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
    if not cfg:
        return None
    try:
        validated = ProviderSettingsService._validate_telnyx_config(dict(cfg))
    except Exception:
        validated = dict(cfg)
    raw = str(validated.get("whatsapp_from") or validated.get("whatsapp_number") or "").strip()
    if not raw:
        return None
    try:
        return normalize_telnyx_e164(raw)
    except ValueError:
        return raw if raw.startswith("+") else None


def cache_feedback_wa_sender(db: Session, *, country_code: str, phone_e164: str) -> None:
    zone = country_to_zone(country_code) or str(country_code or "gb").strip().lower() or "gb"
    row = db.execute(
        select(FeedbackWaSender).where(FeedbackWaSender.country_code == zone)
    ).scalar_one_or_none()
    now = datetime.utcnow()
    if row is None:
        db.add(
            FeedbackWaSender(
                id=str(uuid.uuid4()),
                country_code=zone,
                phone_e164=phone_e164,
                created_at=now,
            )
        )
    elif row.phone_e164 != phone_e164:
        row.phone_e164 = phone_e164
        row.updated_at = now
        db.add(row)
    db.flush()


def sync_feedback_wa_senders_from_telnyx(db: Session) -> str | None:
    """Copy resolved whatsapp_from into feedback_wa_senders for all market zones."""
    phone = get_telnyx_whatsapp_from_e164(db)
    if not phone:
        return None
    for zone in ("gb", "eu", "us", "ca", "au"):
        cache_feedback_wa_sender(db, country_code=zone, phone_e164=phone)
    return phone


def resolve_feedback_wa_phone_for_qr(db: Session, country_code: str, *, org_id: str | None = None) -> str:
    """Connection profile number first — same number used for outbound feedback replies."""
    phone = get_telnyx_whatsapp_from_e164(db, org_id=org_id)
    if phone:
        cache_feedback_wa_sender(db, country_code=country_code, phone_e164=phone)
        return phone

    zone = country_to_zone(country_code) or str(country_code or "gb").strip().lower() or "gb"
    sender = db.execute(
        select(FeedbackWaSender).where(FeedbackWaSender.country_code == zone)
    ).scalar_one_or_none()
    if sender and sender.phone_e164 and sender.phone_e164 != PLACEHOLDER_WA_E164:
        return sender.phone_e164

    raise ValueError(
        "WhatsApp business number is not configured. "
        "Open Admin → Connection Profiles and set an active Default WhatsApp profile, "
        "or configure Telnyx / Meta under Integrations."
    )
