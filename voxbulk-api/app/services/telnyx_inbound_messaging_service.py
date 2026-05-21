from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.whatsapp_log import WhatsAppLog
from app.services.messaging_log_service import LogService, normalize_e164
from app.services.provider_settings import ProviderSettingsService


def _phone_from(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("phone_number") or value.get("number") or "").strip()
    return str(value or "").strip()


def _extract_message_text(record: dict[str, Any]) -> str:
    text = record.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    body = record.get("body")
    if isinstance(body, str) and body.strip():
        return body.strip()
    if isinstance(body, dict):
        inner = body.get("text")
        if isinstance(inner, str) and inner.strip():
            return inner.strip()
        if isinstance(inner, dict):
            nested = inner.get("body")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        if str(body.get("type") or "").lower() == "text":
            text_obj = body.get("text")
            if isinstance(text_obj, dict):
                nested = text_obj.get("body")
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()

    whatsapp_message = record.get("whatsapp_message")
    if isinstance(whatsapp_message, dict):
        if str(whatsapp_message.get("type") or "").lower() == "text":
            text_obj = whatsapp_message.get("text")
            if isinstance(text_obj, dict):
                nested = text_obj.get("body")
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()

    return ""


def _resolve_org_id(db: Session, *, header_org_id: str | None, config: dict[str, Any]) -> str:
    for candidate in (
        str(header_org_id or "").strip(),
        str(config.get("messaging_org_id") or "").strip(),
        str(config.get("default_messaging_org_id") or "").strip(),
    ):
        if not candidate:
            continue
        row = db.execute(select(Organisation.id).where(Organisation.id == candidate)).scalar_one_or_none()
        if row:
            return candidate
    fallback = db.execute(select(Organisation.id).order_by(Organisation.created_at.asc()).limit(1)).scalar_one_or_none()
    if fallback:
        return str(fallback)
    raise ValueError("No organisation found to attach inbound Telnyx messages — create an org or set messaging_org_id in Telnyx settings.")


def _message_channel(msg_type: str) -> str:
    clean = str(msg_type or "").strip().lower()
    return "whatsapp" if "whatsapp" in clean else "sms"


class TelnyxInboundMessagingService:
    @staticmethod
    def handle_webhook(db: Session, payload: dict[str, Any], *, header_org_id: str | None = None) -> dict[str, Any]:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        event_type = str(data.get("event_type") or payload.get("event_type") or "").strip().lower()
        record = data.get("payload") if isinstance(data.get("payload"), dict) else data

        if event_type and event_type not in {"message.received", "message.sent", "message.finalized"}:
            return {"ok": True, "ignored": True, "event_type": event_type}

        message_id = str(record.get("id") or record.get("message_id") or "").strip() or None
        direction = str(record.get("direction") or "inbound").strip().lower()
        msg_type = str(record.get("type") or record.get("record_type") or "SMS")
        channel = _message_channel(msg_type)

        from_number = _phone_from(record.get("from"))
        to_entries = record.get("to")
        to_number = ""
        if isinstance(to_entries, list) and to_entries:
            to_number = _phone_from(to_entries[0])
        elif isinstance(to_entries, dict):
            to_number = _phone_from(to_entries)

        body = _extract_message_text(record)
        status = str(record.get("status") or ("received" if direction == "inbound" else "sent")).strip().lower()

        if message_id:
            existing = db.execute(
                select(WhatsAppLog).where(
                    WhatsAppLog.provider == "telnyx",
                    WhatsAppLog.external_message_id == message_id,
                )
            ).scalar_one_or_none()
            if existing is not None:
                if status and status != existing.status:
                    existing.status = status
                    if body and not existing.body:
                        existing.body = body
                    db.add(existing)
                    db.commit()
                if direction == "outbound":
                    try:
                        from app.services.telephony_recovery_bridge import apply_message_status_to_recovery

                        for provider in ("telnyx_whatsapp", "telnyx_sms"):
                            apply_message_status_to_recovery(
                                db,
                                provider=provider,
                                provider_ref=message_id,
                                message_status=status,
                            )
                        db.commit()
                    except Exception:
                        pass
                return {"ok": True, "log_id": existing.id, "duplicate": True, "status": status}

        if direction != "inbound" and event_type != "message.received":
            if direction == "outbound" and event_type in {"message.sent", "message.finalized"} and message_id:
                pass
            else:
                return {"ok": True, "ignored": True, "event_type": event_type, "direction": direction}

        cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
        config = cfg if isinstance(cfg, dict) else {}
        org_id = _resolve_org_id(db, header_org_id=header_org_id, config=config)

        try:
            from_norm = normalize_e164(from_number) if from_number else from_number
        except ValueError:
            from_norm = from_number
        try:
            to_norm = normalize_e164(to_number) if to_number else to_number
        except ValueError:
            to_norm = to_number

        media = record.get("media")
        media_json = json.dumps(media, ensure_ascii=False)[:8000] if media else None
        raw_payload = json.dumps(payload, ensure_ascii=False)[:8000]

        row = WhatsAppLog(
            org_id=org_id,
            provider="telnyx",
            external_message_id=message_id,
            status=status or ("received" if direction == "inbound" else "sent"),
            direction="inbound" if direction == "inbound" else "outbound",
            to_number=to_norm or None,
            from_number=from_norm or None,
            body=body or f"({channel} message)",
            media_json=media_json,
            raw_payload=raw_payload,
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        if message_id and direction == "outbound":
            try:
                from app.services.telephony_recovery_bridge import apply_message_status_to_recovery

                for provider in ("telnyx_whatsapp", "telnyx_sms"):
                    apply_message_status_to_recovery(
                        db,
                        provider=provider,
                        provider_ref=message_id,
                        message_status=status,
                    )
                db.commit()
            except Exception:
                pass

        return {"ok": True, "log_id": row.id, "channel": channel, "org_id": org_id}
