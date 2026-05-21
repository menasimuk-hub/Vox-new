from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.http_ssl import httpx_ssl_verify
from app.models.whatsapp_log import WhatsAppLog
from app.services.provider_settings import ProviderSettingsService
from app.services.telnyx_api_key import normalize_telnyx_api_key, normalize_telnyx_e164, require_telnyx_api_key
from app.services.telnyx_voice_service import _telnyx_config, _telnyx_headers, _telnyx_http_error_detail, TelnyxConfigError
from app.services.messaging_log_service import LogService, normalize_e164


TELNYX_MESSAGES_URL = "https://api.telnyx.com/v2/messages"
TELNYX_WHATSAPP_MESSAGES_URL = "https://api.telnyx.com/v2/messages/whatsapp"


@dataclass(frozen=True)
class TelnyxMessageResult:
    ok: bool
    status: str
    external_id: str | None = None
    detail: str | None = None
    channel: str = "sms"
    payload: dict[str, Any] | None = None


class TelnyxMessagingService:
    @staticmethod
    def _config(db: Session) -> dict[str, Any]:
        try:
            return _telnyx_config(db)
        except TelnyxConfigError as e:
            raise ValueError(str(e)) from e

    @staticmethod
    def _from_numbers(config: dict[str, Any]) -> tuple[str, str | None]:
        sms_from = str(
            config.get("sms_from")
            or config.get("default_outbound_number")
            or config.get("fallback_caller_id")
            or ""
        ).strip()
        wa_from = str(config.get("whatsapp_from") or config.get("whatsapp_number") or "").strip()
        return sms_from, wa_from or None

    @staticmethod
    def _request_message(
        db: Session,
        *,
        url: str,
        payload: dict[str, Any],
        channel: str,
        include_messaging_profile: bool = True,
    ) -> TelnyxMessageResult:
        config = TelnyxMessagingService._config(db)
        api_key = normalize_telnyx_api_key(str(config.get("api_key") or ""))
        if not api_key:
            api_key, _ = require_telnyx_api_key(db)

        if include_messaging_profile:
            messaging_profile_id = str(config.get("messaging_profile_id") or "").strip()
            if messaging_profile_id and "messaging_profile_id" not in payload:
                payload["messaging_profile_id"] = messaging_profile_id

        try:
            with httpx.Client(timeout=20.0, verify=httpx_ssl_verify()) as client:
                response = client.post(url, json=payload, headers=_telnyx_headers(api_key))
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as e:
            return TelnyxMessageResult(
                ok=False,
                status="http_error",
                detail=_telnyx_http_error_detail(e),
                channel=channel,
            )
        except Exception as e:
            return TelnyxMessageResult(ok=False, status="error", detail=str(e), channel=channel)

        data = body.get("data") if isinstance(body, dict) else {}
        if not isinstance(data, dict):
            data = {}
        msg_id = str(data.get("id") or data.get("message_id") or "") or None
        msg_status = str(data.get("status") or "queued")
        return TelnyxMessageResult(
            ok=True,
            status=msg_status,
            external_id=msg_id,
            channel=channel,
            payload=body if isinstance(body, dict) else None,
        )

    @staticmethod
    def _post_message(db: Session, payload: dict[str, Any]) -> TelnyxMessageResult:
        return TelnyxMessagingService._request_message(
            db,
            url=TELNYX_MESSAGES_URL,
            payload=payload,
            channel=str(payload.get("type") or "sms").lower(),
        )

    @staticmethod
    def _build_whatsapp_message(
        *,
        body: str,
        template_name: str | None = None,
        template_id: str | None = None,
        template_language: str | None = None,
        template_components: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        template_id = str(template_id or "").strip() or None
        template_name = str(template_name or "").strip() or None
        if template_id or template_name:
            template: dict[str, Any] = {}
            if template_id:
                template["template_id"] = template_id
            else:
                template["name"] = template_name
                lang = str(template_language or "en_US").strip() or "en_US"
                template["language"] = {"policy": "deterministic", "code": lang}
            if template_components:
                template["components"] = template_components
            return {"type": "template", "template": template}

        text_body = str(body or "").strip()
        if not text_body:
            raise ValueError("WhatsApp message body is required unless a template is provided.")
        return {"type": "text", "text": {"body": text_body}}

    @staticmethod
    def send_sms(db: Session, *, to_number: str, body: str, from_number: str | None = None) -> TelnyxMessageResult:
        config = TelnyxMessagingService._config(db)
        sms_from, _ = TelnyxMessagingService._from_numbers(config)
        sender = normalize_telnyx_e164(from_number or sms_from)
        recipient = normalize_telnyx_e164(to_number)
        if not sender:
            return TelnyxMessageResult(
                ok=False,
                status="not_configured",
                detail="Telnyx SMS from-number is not configured (set default_outbound_number in admin Integrations).",
                channel="sms",
            )
        if not recipient:
            return TelnyxMessageResult(ok=False, status="invalid_to", detail="Recipient phone number is invalid.", channel="sms")
        return TelnyxMessagingService._post_message(
            db,
            {"from": sender, "to": recipient, "text": str(body or ""), "type": "SMS"},
        )

    @staticmethod
    def send_whatsapp(
        db: Session,
        *,
        to_number: str,
        body: str,
        from_number: str | None = None,
        template_name: str | None = None,
        template_id: str | None = None,
        template_language: str | None = None,
        template_components: list[dict[str, Any]] | None = None,
    ) -> TelnyxMessageResult:
        config = TelnyxMessagingService._config(db)
        _, wa_from = TelnyxMessagingService._from_numbers(config)
        sender_raw = from_number or wa_from
        if not sender_raw:
            return TelnyxMessageResult(
                ok=False,
                status="not_configured",
                detail="Telnyx WhatsApp from-number is not configured (set whatsapp_from in admin Integrations).",
                channel="whatsapp",
            )
        sender = normalize_telnyx_e164(sender_raw)
        recipient = normalize_telnyx_e164(to_number)
        if not sender:
            return TelnyxMessageResult(
                ok=False,
                status="invalid_from",
                detail="WhatsApp from-number is invalid.",
                channel="whatsapp",
            )
        if not recipient:
            return TelnyxMessageResult(ok=False, status="invalid_to", detail="Recipient phone number is invalid.", channel="whatsapp")

        try:
            whatsapp_message = TelnyxMessagingService._build_whatsapp_message(
                body=body,
                template_name=template_name,
                template_id=template_id,
                template_language=template_language,
                template_components=template_components,
            )
        except ValueError as e:
            return TelnyxMessageResult(ok=False, status="invalid_payload", detail=str(e), channel="whatsapp")

        return TelnyxMessagingService._request_message(
            db,
            url=TELNYX_WHATSAPP_MESSAGES_URL,
            payload={"from": sender, "to": recipient, "whatsapp_message": whatsapp_message},
            channel="whatsapp",
            include_messaging_profile=False,
        )

    @staticmethod
    def send_survey_message(
        db: Session,
        *,
        org_id: str,
        to_number: str,
        body: str,
        prefer_whatsapp: bool = True,
    ) -> TelnyxMessageResult:
        """Try WhatsApp first when requested; fall back to SMS if WA is unavailable."""
        wa_result: TelnyxMessageResult | None = None
        if prefer_whatsapp:
            wa_result = TelnyxMessagingService.send_whatsapp(db, to_number=to_number, body=body)
            if wa_result.ok:
                return wa_result
        sms = TelnyxMessagingService.send_sms(db, to_number=to_number, body=body)
        if sms.ok:
            note = f"WhatsApp unavailable; sent via SMS. {wa_result.detail}" if wa_result and wa_result.detail else None
            return TelnyxMessageResult(
                ok=True,
                status=sms.status,
                external_id=sms.external_id,
                detail=note,
                channel="sms",
                payload=sms.payload,
            )
        parts = [p.detail for p in (wa_result, sms) if p and p.detail]
        detail = " · ".join(parts) or "Could not send message via Telnyx."
        return TelnyxMessageResult(ok=False, status="failed", detail=detail, channel="whatsapp" if prefer_whatsapp else "sms")

    @staticmethod
    def log_outbound(
        db: Session,
        *,
        org_id: str,
        to_number: str,
        from_number: str | None,
        body: str,
        result: TelnyxMessageResult,
    ) -> WhatsAppLog:
        LogService._validate_optional_relations(db, org_id)
        row = WhatsAppLog(
            org_id=org_id,
            provider="telnyx",
            external_message_id=result.external_id,
            status=result.status if result.ok else "failed",
            direction="outbound",
            to_number=normalize_e164(to_number) or to_number,
            from_number=from_number,
            body=body,
            raw_payload=json.dumps(result.payload or {"detail": result.detail}, ensure_ascii=False)[:8000],
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def is_configured(db: Session) -> dict[str, bool]:
        try:
            cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
            if not enabled:
                return {"enabled": False, "sms": False, "whatsapp": False}
            config = ProviderSettingsService._validate_telnyx_config(cfg or {})
            sms_from, wa_from = TelnyxMessagingService._from_numbers(config)
            api_key, _ = require_telnyx_api_key(db)
            return {
                "enabled": bool(api_key),
                "sms": bool(api_key and sms_from),
                "whatsapp": bool(api_key and wa_from),
            }
        except Exception:
            return {"enabled": False, "sms": False, "whatsapp": False}
