from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
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
from app.services.connection.connection_profile_seed_service import ConnectionProfileSeedService
from app.services.connection.constants import ALL_SERVICE_CODES, normalize_service_code
from app.services.connection.profile_credentials import (
    meta_config_from_profile,
    telnyx_config_from_profile,
)
from app.services.connection.providers.whatsapp_meta import WhatsappMetaProvider
from app.services.connection.providers.whatsapp_telnyx import WhatsappTelnyxProvider
from app.services.meta_whatsapp_service import MetaWhatsappService
from app.services.telnyx_api_key import normalize_telnyx_api_key


class ConnectionProfileError(ValueError):
    pass


class ConnectionProfilesAdminService:
    SECRET_FIELDS = {
        "telnyx_api_key",
        "meta_access_token",
        "meta_app_secret",
        "meta_webhook_verify_token",
    }

    @staticmethod
    def list_profiles(db: Session, *, channel: str | None = None) -> list[dict[str, Any]]:
        ConnectionProfileSeedService.ensure_seeded(db)
        stmt = select(ConnectionProfile).order_by(ConnectionProfile.is_default.desc(), ConnectionProfile.name.asc())
        if channel:
            stmt = stmt.where(ConnectionProfile.channel == str(channel).strip().lower())
        rows = list(db.execute(stmt).scalars().all())
        return [ConnectionProfilesAdminService._serialize(db, row) for row in rows]

    @staticmethod
    def get_profile(db: Session, profile_id: str) -> dict[str, Any] | None:
        row = db.get(ConnectionProfile, profile_id)
        if row is None:
            return None
        return ConnectionProfilesAdminService._serialize(db, row)

    @staticmethod
    def create_profile(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        channel = str(payload.get("channel") or CHANNEL_WHATSAPP).strip().lower()
        provider = str(payload.get("provider") or PROVIDER_TELNYX).strip().lower()
        if channel not in {CHANNEL_WHATSAPP, CHANNEL_CALLING}:
            raise ConnectionProfileError("Invalid channel")
        if provider not in {PROVIDER_TELNYX, PROVIDER_META}:
            raise ConnectionProfileError("Invalid provider")
        if channel == CHANNEL_CALLING and provider != PROVIDER_TELNYX:
            raise ConnectionProfileError("Calling profiles must use Telnyx")

        now = datetime.utcnow()
        row = ConnectionProfile(
            id=str(uuid.uuid4()),
            name=str(payload.get("name") or "New profile").strip() or "New profile",
            channel=channel,
            provider=provider,
            is_default=bool(payload.get("is_default")),
            is_active=bool(payload.get("is_active", True)),
            created_at=now,
            updated_at=now,
        )
        ConnectionProfilesAdminService._apply_payload(row, payload)
        if row.is_default:
            ConnectionProfilesAdminService._clear_default(db, channel=channel, exclude_id=None)
        db.add(row)
        db.flush()
        ConnectionProfilesAdminService._upsert_services(db, row.id, payload.get("services") or {})
        ConnectionProfilesAdminService._upsert_orgs(db, row.id, payload.get("org_ids") or [])
        db.commit()
        db.refresh(row)
        return ConnectionProfilesAdminService._serialize(db, row)

    @staticmethod
    def update_profile(db: Session, profile_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = db.get(ConnectionProfile, profile_id)
        if row is None:
            raise ConnectionProfileError("Profile not found")
        if "name" in payload:
            row.name = str(payload.get("name") or row.name).strip() or row.name
        if "is_active" in payload:
            row.is_active = bool(payload["is_active"])
        if "is_default" in payload and bool(payload["is_default"]):
            ConnectionProfilesAdminService._clear_default(db, channel=row.channel, exclude_id=row.id)
            row.is_default = True
        elif "is_default" in payload:
            row.is_default = bool(payload["is_default"])
        ConnectionProfilesAdminService._apply_payload(row, payload)
        row.updated_at = datetime.utcnow()
        if "services" in payload:
            ConnectionProfilesAdminService._upsert_services(db, row.id, payload.get("services") or {})
        if "org_ids" in payload:
            ConnectionProfilesAdminService._upsert_orgs(db, row.id, payload.get("org_ids") or [])
        db.add(row)
        db.commit()
        db.refresh(row)
        return ConnectionProfilesAdminService._serialize(db, row)

    @staticmethod
    def delete_profile(db: Session, profile_id: str) -> None:
        row = db.get(ConnectionProfile, profile_id)
        if row is None:
            raise ConnectionProfileError("Profile not found")
        if row.is_default:
            raise ConnectionProfileError("Cannot delete the default profile")
        db.delete(row)
        db.commit()

    @staticmethod
    def test_profile(db: Session, profile_id: str, *, to_number: str | None = None) -> dict[str, Any]:
        row = db.get(ConnectionProfile, profile_id)
        if row is None:
            raise ConnectionProfileError("Profile not found")
        now = datetime.utcnow()
        detail = ""
        ok = False
        status = "failed"

        if row.channel == CHANNEL_WHATSAPP and row.provider == PROVIDER_TELNYX:
            config = telnyx_config_from_profile(row)
            api_key = normalize_telnyx_api_key(str(config.get("api_key") or ""))
            if not api_key:
                detail = "Telnyx API key is not configured on this profile"
            elif not config.get("whatsapp_from"):
                detail = "WhatsApp from-number is not configured"
            else:
                ok = True
                status = "ok"
                detail = f"Telnyx WhatsApp profile configured ({config.get('whatsapp_from')})"
                if to_number:
                    result = WhatsappTelnyxProvider.send(
                        db,
                        config=config,
                        to_number=to_number,
                        body="VoxBulk connection profile test",
                        from_number=config.get("whatsapp_from"),
                        meter_usage=False,
                    )
                    ok = result.ok
                    status = result.status if result.ok else "failed"
                    detail = result.detail or detail

        elif row.channel == CHANNEL_WHATSAPP and row.provider == PROVIDER_META:
            config = meta_config_from_profile(row)
            test = MetaWhatsappService.test_connection_with_config(config)
            ok = bool(test.get("ok"))
            status = str(test.get("status") or ("ok" if ok else "failed"))
            detail = str(test.get("detail") or "")
            if ok and to_number:
                result = WhatsappMetaProvider.send(
                    db,
                    config=config,
                    to_number=to_number,
                    body="VoxBulk connection profile test",
                    meter_usage=False,
                )
                ok = result.ok
                status = result.status if result.ok else "failed"
                detail = result.detail or detail

        elif row.channel == CHANNEL_CALLING:
            config = telnyx_config_from_profile(row)
            if not normalize_telnyx_api_key(str(config.get("api_key") or "")):
                detail = "Telnyx API key is not configured"
            elif not row.calling_number:
                detail = "Calling number is not configured"
            else:
                ok = True
                status = "ok"
                detail = f"Calling line configured ({row.calling_number})"
        else:
            detail = f"Unsupported profile type: {row.channel}/{row.provider}"

        row.last_test_at = now
        row.last_test_status = status
        row.last_test_detail = detail[:4000]
        row.updated_at = now
        db.add(row)
        db.commit()
        return {"ok": ok, "status": status, "detail": detail}

    @staticmethod
    def webhook_urls() -> dict[str, str]:
        return {
            "telnyx_whatsapp": "https://api.voxbulk.com/telnyx/webhooks/messages",
            "meta_whatsapp": "https://api.voxbulk.com/webhooks/meta/whatsapp",
        }

    @staticmethod
    def _clear_default(db: Session, *, channel: str, exclude_id: str | None) -> None:
        stmt = select(ConnectionProfile).where(ConnectionProfile.channel == channel).where(ConnectionProfile.is_default.is_(True))
        for row in db.execute(stmt).scalars().all():
            if exclude_id and row.id == exclude_id:
                continue
            row.is_default = False
            row.updated_at = datetime.utcnow()
            db.add(row)

    @staticmethod
    def _apply_payload(row: ConnectionProfile, payload: dict[str, Any]) -> None:
        enc = get_encryptor()
        for field, attr in (
            ("telnyx_messaging_profile_id", "telnyx_messaging_profile_id"),
            ("telnyx_number", "telnyx_number"),
            ("telnyx_connection_id", "telnyx_connection_id"),
            ("telnyx_outbound_voice_profile_id", "telnyx_outbound_voice_profile_id"),
            ("meta_waba_id", "meta_waba_id"),
            ("meta_phone_number_id", "meta_phone_number_id"),
            ("meta_business_id", "meta_business_id"),
            ("meta_whatsapp_from", "meta_whatsapp_from"),
            ("calling_number", "calling_number"),
            ("label", "label"),
        ):
            if field in payload:
                setattr(row, attr, str(payload.get(field) or "").strip() or None)

        if "regions" in payload:
            regions = payload.get("regions")
            if isinstance(regions, list):
                row.regions_json = json.dumps([str(x).strip() for x in regions if str(x).strip()])
            else:
                row.regions_json = str(regions or "").strip() or None

        if "telnyx_api_key" in payload and str(payload.get("telnyx_api_key") or "").strip():
            row.telnyx_api_key_encrypted = enc.encrypt_str(str(payload["telnyx_api_key"]).strip())
        for secret_key, col in (
            ("meta_access_token", "meta_access_token_encrypted"),
            ("meta_app_secret", "meta_app_secret_encrypted"),
            ("meta_webhook_verify_token", "meta_webhook_verify_token_encrypted"),
        ):
            if secret_key in payload and str(payload.get(secret_key) or "").strip():
                setattr(row, col, enc.encrypt_str(str(payload[secret_key]).strip()))

    @staticmethod
    def _upsert_services(db: Session, profile_id: str, services: dict[str, Any]) -> None:
        if not services:
            return
        for raw_code, enabled in services.items():
            code = normalize_service_code(raw_code)
            if not code or code not in ALL_SERVICE_CODES:
                continue
            row = db.execute(
                select(ConnectionProfileService)
                .where(ConnectionProfileService.profile_id == profile_id)
                .where(ConnectionProfileService.service_code == code)
            ).scalar_one_or_none()
            now = datetime.utcnow()
            if row is None:
                db.add(
                    ConnectionProfileService(
                        id=str(uuid.uuid4()),
                        profile_id=profile_id,
                        service_code=code,
                        enabled=bool(enabled),
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                row.enabled = bool(enabled)
                row.updated_at = now
                db.add(row)

    @staticmethod
    def _upsert_orgs(db: Session, profile_id: str, org_ids: list[str]) -> None:
        if org_ids is None:
            return
        cleaned = [str(x).strip() for x in org_ids if str(x).strip()]
        db.execute(delete(ConnectionProfileOrg).where(ConnectionProfileOrg.profile_id == profile_id))
        now = datetime.utcnow()
        for org_id in cleaned:
            db.add(
                ConnectionProfileOrg(
                    id=str(uuid.uuid4()),
                    profile_id=profile_id,
                    org_id=org_id,
                    created_at=now,
                )
            )

    @staticmethod
    def _serialize(db: Session, row: ConnectionProfile) -> dict[str, Any]:
        services = {
            svc.service_code: svc.enabled
            for svc in db.execute(
                select(ConnectionProfileService).where(ConnectionProfileService.profile_id == row.id)
            ).scalars().all()
        }
        for code in ALL_SERVICE_CODES:
            services.setdefault(code, True)
        org_ids = [
            str(x)
            for x in db.execute(
                select(ConnectionProfileOrg.org_id).where(ConnectionProfileOrg.profile_id == row.id)
            ).scalars().all()
        ]
        return {
            "id": row.id,
            "name": row.name,
            "channel": row.channel,
            "provider": row.provider,
            "is_default": row.is_default,
            "is_active": row.is_active,
            "telnyx_messaging_profile_id": row.telnyx_messaging_profile_id,
            "telnyx_number": row.telnyx_number,
            "telnyx_connection_id": row.telnyx_connection_id,
            "telnyx_outbound_voice_profile_id": row.telnyx_outbound_voice_profile_id,
            "meta_waba_id": row.meta_waba_id,
            "meta_phone_number_id": row.meta_phone_number_id,
            "meta_business_id": row.meta_business_id,
            "meta_whatsapp_from": row.meta_whatsapp_from,
            "calling_number": row.calling_number,
            "regions": json.loads(row.regions_json) if row.regions_json else [],
            "label": row.label,
            "has_telnyx_api_key": bool(row.telnyx_api_key_encrypted),
            "has_meta_access_token": bool(row.meta_access_token_encrypted),
            "has_meta_app_secret": bool(row.meta_app_secret_encrypted),
            "has_meta_webhook_verify_token": bool(row.meta_webhook_verify_token_encrypted),
            "last_test_at": row.last_test_at.isoformat() if row.last_test_at else None,
            "last_test_status": row.last_test_status,
            "last_test_detail": row.last_test_detail,
            "services": services,
            "org_ids": org_ids,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
