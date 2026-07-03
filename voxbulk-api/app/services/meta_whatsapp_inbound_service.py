from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.services.messaging_log_service import LogService, normalize_e164
from app.services.meta_whatsapp_config_service import validate_meta_whatsapp_config
from app.services.provider_settings import ProviderSettingsService

logger = logging.getLogger(__name__)


def _extract_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return out
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            messages = value.get("messages")
            if isinstance(messages, list):
                metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
                for msg in messages:
                    if isinstance(msg, dict):
                        out.append({"message": msg, "metadata": metadata, "waba_id": entry.get("id")})
    return out


class MetaWhatsappInboundService:
    @staticmethod
    def handle_webhook(db: Session, *, payload: dict[str, Any]) -> dict[str, Any]:
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="meta_whatsapp")
        config = validate_meta_whatsapp_config(cfg or {})
        org_id = str(config.get("default_messaging_org_id") or "").strip() or None
        if not org_id:
            from sqlalchemy import select

            from app.models.organisation import Organisation

            row = db.scalar(select(Organisation.id).limit(1))
            org_id = str(row).strip() if row else ""
        if not org_id:
            logger.warning("meta_whatsapp_inbound_no_org")
            return {"ok": True, "logged": 0}

        logged = 0
        for item in _extract_messages(payload):
            msg = item.get("message") if isinstance(item.get("message"), dict) else {}
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            from_phone = normalize_e164(str(msg.get("from") or ""))
            body = ""
            msg_type = str(msg.get("type") or "").strip().lower()
            if msg_type == "text":
                text = msg.get("text")
                if isinstance(text, dict):
                    body = str(text.get("body") or "").strip()
            elif msg_type:
                body = f"[{msg_type} message]"
            if not from_phone:
                continue
            try:
                LogService.create_whatsapp_log(
                    db,
                    org_id=org_id,
                    direction="inbound",
                    from_number=from_phone,
                    to_number=normalize_e164(str(metadata.get("display_phone_number") or config.get("whatsapp_from") or "")),
                    body=body or "(no text)",
                    status="received",
                    external_message_id=str(msg.get("id") or "").strip() or None,
                    provider="meta_whatsapp",
                    raw_payload=json.dumps(msg, ensure_ascii=False),
                )
                logged += 1
            except Exception:
                logger.exception("meta_whatsapp_inbound_log_failed from=%s", from_phone)
        return {"ok": True, "logged": logged}
