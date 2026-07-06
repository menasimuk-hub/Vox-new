from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.encryption import get_encryptor
from app.models.connection_profile import (
    CHANNEL_CALLING,
    CHANNEL_WHATSAPP,
    PROVIDER_META,
    PROVIDER_TELNYX,
    ConnectionProfile,
    ConnectionProfileOrg,
    ConnectionProfileService,
)
from app.services.connection.constants import ALL_SERVICE_CODES
from app.services.provider_settings import ProviderSettingsService


class ConnectionProfileSeedService:
    @staticmethod
    def ensure_seeded(db: Session) -> dict[str, Any]:
        existing = db.execute(select(func.count()).select_from(ConnectionProfile)).scalar_one()
        if int(existing or 0) > 0:
            return {"seeded": False, "reason": "profiles_exist"}

        enc = get_encryptor()
        now = datetime.utcnow()
        created: list[str] = []

        telnyx_cfg, telnyx_enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
        telnyx_cfg = telnyx_cfg or {}
        if telnyx_enabled and telnyx_cfg:
            wa_id = str(uuid.uuid4())
            wa_profile = ConnectionProfile(
                id=wa_id,
                name="Default Shared Pool",
                channel=CHANNEL_WHATSAPP,
                provider=PROVIDER_TELNYX,
                is_default=True,
                is_active=True,
                telnyx_api_key_encrypted=enc.encrypt_str(str(telnyx_cfg.get("api_key") or "")) if telnyx_cfg.get("api_key") else None,
                telnyx_messaging_profile_id=str(
                    telnyx_cfg.get("whatsapp_messaging_profile_id") or telnyx_cfg.get("messaging_profile_id") or ""
                ).strip()
                or None,
                telnyx_number=str(telnyx_cfg.get("whatsapp_from") or telnyx_cfg.get("whatsapp_number") or "").strip() or None,
                telnyx_connection_id=str(telnyx_cfg.get("connection_id") or "").strip() or None,
                telnyx_outbound_voice_profile_id=str(telnyx_cfg.get("outbound_voice_profile_id") or "").strip() or None,
                created_at=now,
                updated_at=now,
            )
            db.add(wa_profile)
            ConnectionProfileSeedService._seed_services(db, wa_id, now)
            created.append(wa_id)

            call_id = str(uuid.uuid4())
            call_profile = ConnectionProfile(
                id=call_id,
                name="Default Calling Line",
                channel=CHANNEL_CALLING,
                provider=PROVIDER_TELNYX,
                is_default=True,
                is_active=True,
                telnyx_api_key_encrypted=wa_profile.telnyx_api_key_encrypted,
                telnyx_connection_id=wa_profile.telnyx_connection_id,
                telnyx_outbound_voice_profile_id=wa_profile.telnyx_outbound_voice_profile_id,
                calling_number=str(telnyx_cfg.get("voice_from") or telnyx_cfg.get("from_number") or "").strip() or None,
                label="Platform default",
                created_at=now,
                updated_at=now,
            )
            db.add(call_profile)
            created.append(call_id)

        meta_cfg, meta_enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="meta_whatsapp")
        meta_cfg = meta_cfg or {}
        if meta_enabled and meta_cfg.get("phone_number_id"):
            meta_id = str(uuid.uuid4())
            meta_profile = ConnectionProfile(
                id=meta_id,
                name="Meta WhatsApp",
                channel=CHANNEL_WHATSAPP,
                provider=PROVIDER_META,
                is_default=False,
                is_active=True,
                meta_waba_id=str(meta_cfg.get("waba_id") or "").strip() or None,
                meta_phone_number_id=str(meta_cfg.get("phone_number_id") or "").strip() or None,
                meta_business_id=str(meta_cfg.get("business_id") or "").strip() or None,
                meta_access_token_encrypted=enc.encrypt_str(str(meta_cfg.get("access_token") or ""))
                if meta_cfg.get("access_token")
                else None,
                meta_app_secret_encrypted=enc.encrypt_str(str(meta_cfg.get("app_secret") or ""))
                if meta_cfg.get("app_secret")
                else None,
                meta_webhook_verify_token_encrypted=enc.encrypt_str(str(meta_cfg.get("webhook_verify_token") or ""))
                if meta_cfg.get("webhook_verify_token")
                else None,
                meta_whatsapp_from=str(meta_cfg.get("whatsapp_from") or "").strip() or None,
                created_at=now,
                updated_at=now,
            )
            db.add(meta_profile)
            ConnectionProfileSeedService._seed_services(db, meta_id, now)
            created.append(meta_id)

        if created:
            db.commit()
        return {"seeded": bool(created), "profile_ids": created}

    @staticmethod
    def _seed_services(db: Session, profile_id: str, now: datetime) -> None:
        for code in ALL_SERVICE_CODES:
            db.add(
                ConnectionProfileService(
                    id=str(uuid.uuid4()),
                    profile_id=profile_id,
                    service_code=code,
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                )
            )
