from __future__ import annotations

import json
import logging
import re
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

logger = logging.getLogger(__name__)


TELNYX_MESSAGES_URL = "https://api.telnyx.com/v2/messages"
TELNYX_WHATSAPP_MESSAGES_URL = "https://api.telnyx.com/v2/messages/whatsapp"
_TEMPLATE_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-", re.IGNORECASE)


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
        sms_from = str(config.get("sms_from") or "").strip()
        wa_from = str(config.get("whatsapp_from") or config.get("whatsapp_number") or "").strip()
        return sms_from, wa_from or None

    @staticmethod
    def _messaging_profile_for_channel(config: dict[str, Any], channel: str) -> str | None:
        if channel == "whatsapp":
            profile = str(config.get("whatsapp_messaging_profile_id") or "").strip()
            return profile or None
        profile = str(config.get("messaging_profile_id") or config.get("sms_messaging_profile_id") or "").strip()
        return profile or None

    @staticmethod
    def _messaging_webhook_url(config: dict[str, Any]) -> str | None:
        url = str(config.get("messaging_webhook_url") or "").strip()
        if url:
            return url
        base = str(config.get("webhook_base_url") or "").strip().rstrip("/")
        if base:
            return f"{base}/telnyx/webhooks/messages"
        return None

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
            channel = str(channel or "sms").lower()
            messaging_profile_id = TelnyxMessagingService._messaging_profile_for_channel(config, channel)
            if messaging_profile_id and "messaging_profile_id" not in payload:
                payload["messaging_profile_id"] = messaging_profile_id

        safe_payload = json.loads(json.dumps(payload, default=str))
        logger.info(
            "telnyx_message_request channel=%s url=%s payload=%s",
            channel,
            url,
            json.dumps(safe_payload, default=str)[:8000],
        )

        try:
            with httpx.Client(timeout=20.0, verify=httpx_ssl_verify()) as client:
                response = client.post(url, json=payload, headers=_telnyx_headers(api_key))
                response_text = response.text[:8000]
                logger.info(
                    "telnyx_message_response channel=%s status=%s body=%s",
                    channel,
                    response.status_code,
                    response_text,
                )
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as e:
            error_body = ""
            try:
                error_body = e.response.text[:8000]
            except Exception:
                pass
            logger.error(
                "telnyx_message_http_error channel=%s status=%s body=%s",
                channel,
                e.response.status_code if e.response is not None else "?",
                error_body,
            )
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
    def _get_json(db: Session, url: str) -> tuple[dict[str, Any] | None, str | None]:
        config = TelnyxMessagingService._config(db)
        api_key = normalize_telnyx_api_key(str(config.get("api_key") or ""))
        if not api_key:
            api_key, _ = require_telnyx_api_key(db)
        try:
            with httpx.Client(timeout=20.0, verify=httpx_ssl_verify()) as client:
                response = client.get(url, headers=_telnyx_headers(api_key))
                response.raise_for_status()
                body = response.json()
                return (body if isinstance(body, dict) else {"data": body}), None
        except httpx.HTTPStatusError as e:
            return None, _telnyx_http_error_detail(e)
        except Exception as e:
            return None, str(e)

    @staticmethod
    def format_message_errors(errors: Any) -> list[dict[str, Any]]:
        if not isinstance(errors, list):
            return []
        out: list[dict[str, Any]] = []
        for item in errors:
            if not isinstance(item, dict):
                continue
            meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
            out.append(
                {
                    "code": str(item.get("code") or "").strip(),
                    "title": str(item.get("title") or "").strip(),
                    "detail": str(item.get("detail") or "").strip(),
                    "meta": meta,
                }
            )
        return out

    @staticmethod
    def _error_line(error: dict[str, Any]) -> str:
        code = str(error.get("code") or "").strip()
        detail = str(error.get("detail") or error.get("title") or "").strip()
        meta = error.get("meta") if isinstance(error.get("meta"), dict) else {}
        meta_bits = []
        for key in ("whatsapp_error_code", "whatsapp_error_title", "error_user_msg", "error_user_title", "reason", "message"):
            val = str(meta.get(key) or "").strip()
            if val:
                meta_bits.append(val)
        base = f"{code}: {detail}".strip(": ") if code or detail else ""
        if meta_bits:
            return f"{base} — {' · '.join(meta_bits)}".strip(" —")
        return base

    @staticmethod
    def message_detail_from_data(data: dict[str, Any]) -> dict[str, Any]:
        to_entries = data.get("to")
        to_status = ""
        to_errors: list[dict[str, Any]] = []
        if isinstance(to_entries, list) and to_entries and isinstance(to_entries[0], dict):
            first_to = to_entries[0]
            to_status = str(first_to.get("status") or "").strip()
            to_errors = TelnyxMessagingService.format_message_errors(first_to.get("errors"))
        from_obj = data.get("from")
        from_number = ""
        if isinstance(from_obj, dict):
            from_number = str(from_obj.get("phone_number") or from_obj.get("number") or "").strip()
        errors = TelnyxMessagingService.format_message_errors(data.get("errors"))
        if to_errors:
            seen = {(e.get("code"), e.get("detail")) for e in errors}
            for item in to_errors:
                key = (item.get("code"), item.get("detail"))
                if key not in seen:
                    errors.append(item)
                    seen.add(key)
        error_summary = " · ".join(filter(None, [TelnyxMessagingService._error_line(e) for e in errors]))
        return {
            "id": str(data.get("id") or "").strip(),
            "status": to_status or str(data.get("status") or "").strip(),
            "direction": str(data.get("direction") or "").strip(),
            "type": str(data.get("type") or "").strip(),
            "from_number": from_number,
            "to": to_entries if isinstance(to_entries, list) else [],
            "errors": errors,
            "error_summary": error_summary or None,
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "whatsapp_message": data.get("whatsapp_message"),
            "raw": data,
        }

    @staticmethod
    def retrieve_message(db: Session, message_id: str) -> dict[str, Any]:
        mid = str(message_id or "").strip()
        if not mid:
            return {"ok": False, "error": "message_id is required"}
        url = f"{TELNYX_MESSAGES_URL}/{mid}"
        body, err = TelnyxMessagingService._get_json(db, url)
        if err:
            return {"ok": False, "error": err, "message_id": mid}
        data = body.get("data") if isinstance(body, dict) else {}
        if not isinstance(data, dict):
            return {"ok": False, "error": "Unexpected Telnyx response", "message_id": mid}
        detail = TelnyxMessagingService.message_detail_from_data(data)
        detail["ok"] = True
        return detail

    @staticmethod
    def _post_message(db: Session, payload: dict[str, Any]) -> TelnyxMessageResult:
        return TelnyxMessagingService._request_message(
            db,
            url=TELNYX_MESSAGES_URL,
            payload=payload,
            channel=str(payload.get("type") or "sms").lower(),
        )

    @staticmethod
    def resolve_whatsapp_template_ref(
        *,
        template_name: str | None = None,
        template_id: str | None = None,
    ) -> tuple[str | None, str | None]:
        tid = str(template_id or "").strip() or None
        if tid:
            return None, tid
        name = str(template_name or "").strip() or None
        if not name:
            return None, None
        if _TEMPLATE_UUID_RE.match(name):
            return None, name
        return name, None

    @staticmethod
    def validate_whatsapp_template_ref(template_name: str | None, template_id: str | None) -> str | None:
        explicit_id = str(template_id or "").strip()
        if explicit_id:
            # Synced Meta/Telnyx template ids are often numeric — only reject short portal row numbers.
            if explicit_id.isdigit() and len(explicit_id) <= 5:
                return (
                    f"Template '{explicit_id}' looks like a Telnyx portal row number. "
                    "Use Sync WhatsApp templates in admin, or paste the template name (e.g. voxbulk_sales_offer)."
                )
            return None

        name, tid = TelnyxMessagingService.resolve_whatsapp_template_ref(
            template_name=template_name,
            template_id=template_id,
        )
        ref = name or tid
        if ref and ref.isdigit() and len(ref) <= 5:
            return (
                f"Template '{ref}' looks like a list number, not a Meta template. "
                "In Telnyx → WhatsApp → Templates, copy the template name (e.g. voxbulk_sales_offer) "
                "or use Sync WhatsApp templates — not the row number in the portal."
            )
        return None

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
        resolved_name, resolved_id = TelnyxMessagingService.resolve_whatsapp_template_ref(
            template_name=template_name,
            template_id=template_id,
        )
        if resolved_id or resolved_name:
            template: dict[str, Any] = {}
            lang = str(template_language or "en_US").strip() or "en_US"
            if resolved_id:
                template["template_id"] = resolved_id
                template["language"] = {"policy": "deterministic", "code": lang}
            else:
                template["name"] = resolved_name
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
                detail="Telnyx SMS from-number is not configured (set sms_from in admin Integrations).",
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
        org_id: str | None = None,
        meter_usage: bool = True,
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

        if (template_name or template_id) and whatsapp_message.get("type") != "template":
            return TelnyxMessageResult(
                ok=False,
                status="invalid_payload",
                detail="WhatsApp template reference required; plain-text fallback is not allowed for survey sends.",
                channel="whatsapp",
            )

        payload: dict[str, Any] = {
            "from": sender,
            "to": recipient,
            "type": "WHATSAPP",
            "whatsapp_message": whatsapp_message,
        }
        wa_profile = TelnyxMessagingService._messaging_profile_for_channel(config, "whatsapp")
        if wa_profile:
            payload["messaging_profile_id"] = wa_profile
        webhook_url = TelnyxMessagingService._messaging_webhook_url(config)
        if webhook_url:
            payload["webhook_url"] = webhook_url

        result = TelnyxMessagingService._request_message(
            db,
            url=TELNYX_WHATSAPP_MESSAGES_URL,
            payload=payload,
            channel="whatsapp",
            include_messaging_profile=False,
        )
        if result.ok and org_id and meter_usage:
            try:
                from app.services.usage_wallet_service import UsageWalletService

                UsageWalletService.record_whatsapp_usage(db, org_id=org_id, units=1)
            except Exception:
                pass
        return result

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
            wa_result = TelnyxMessagingService.send_whatsapp(db, to_number=to_number, body=body, org_id=org_id)
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

        def _safe_e164(raw: str | None) -> str | None:
            if not raw:
                return None
            try:
                return normalize_telnyx_e164(raw)
            except Exception:
                try:
                    return normalize_e164(raw)
                except Exception:
                    return str(raw).strip() or None

        row = WhatsAppLog(
            org_id=org_id,
            provider="telnyx",
            external_message_id=result.external_id,
            status=result.status if result.ok else "failed",
            direction="outbound",
            to_number=_safe_e164(to_number),
            from_number=_safe_e164(from_number),
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
