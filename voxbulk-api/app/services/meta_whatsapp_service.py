from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.messaging_log_service import LogService, normalize_e164
from app.services.meta_whatsapp_config_service import MetaWhatsappConfigError, graph_api_base, validate_meta_whatsapp_config
from app.services.provider_settings import ProviderSettingsService
from app.services.telnyx_messaging_service import TelnyxMessageResult, TelnyxMessagingService

logger = logging.getLogger(__name__)

_META_RECORD_PREFIX = "meta-"


class MetaWhatsappServiceError(RuntimeError):
    def __init__(self, message: str, *, error_payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.error_payload = error_payload if isinstance(error_payload, dict) else None


class MetaWhatsappService:
    @staticmethod
    def _config(db: Session) -> tuple[dict[str, Any], bool]:
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="meta_whatsapp")
        return validate_meta_whatsapp_config(cfg or {}), bool(enabled)

    @staticmethod
    def _require_token(config: dict[str, Any]) -> str:
        token = str(config.get("access_token") or "").strip()
        if not token:
            raise MetaWhatsappConfigError("Meta access token is not configured")
        return token

    @staticmethod
    def _graph_request(
        *,
        config: dict[str, Any],
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        token = MetaWhatsappService._require_token(config)
        url = f"{graph_api_base(config).rstrip('/')}/{path.lstrip('/')}"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.request(method.upper(), url, headers=headers, json=json_body, params=params)
        except httpx.HTTPError as exc:
            raise MetaWhatsappServiceError(f"Meta Graph API request failed: {exc}") from exc
        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text}
        if response.status_code >= 400:
            err = payload.get("error") if isinstance(payload, dict) else None
            detail = err.get("message") if isinstance(err, dict) else response.text
            code = err.get("code") if isinstance(err, dict) else response.status_code
            raise MetaWhatsappServiceError(
                f"Meta Graph API error ({code}): {detail}",
                error_payload=err if isinstance(err, dict) else None,
            )
        return payload if isinstance(payload, dict) else {"data": payload}

    @staticmethod
    def test_connection(db: Session) -> dict[str, Any]:
        config, enabled = MetaWhatsappService._config(db)
        if not enabled:
            return {"ok": False, "status": "disabled", "detail": "Meta WhatsApp integration is disabled"}
        phone_number_id = str(config.get("phone_number_id") or "").strip()
        waba_id = str(config.get("waba_id") or "").strip()
        if not phone_number_id:
            return {"ok": False, "status": "not_configured", "detail": "phone_number_id is required"}
        try:
            phone = MetaWhatsappService._graph_request(
                config=config,
                method="GET",
                path=phone_number_id,
                params={"fields": "id,display_phone_number,verified_name,quality_rating"},
            )
        except (MetaWhatsappConfigError, MetaWhatsappServiceError) as exc:
            return {"ok": False, "status": "error", "detail": str(exc)}
        return {
            "ok": True,
            "status": "connected",
            "detail": "Meta Graph API connection OK",
            "phone_number_id": phone.get("id") or phone_number_id,
            "display_phone_number": phone.get("display_phone_number"),
            "verified_name": phone.get("verified_name"),
            "quality_rating": phone.get("quality_rating"),
            "waba_id": waba_id or None,
            "graph_api_version": config.get("graph_api_version"),
        }

    @staticmethod
    def list_templates(db: Session, *, limit: int = 5, status: str = "APPROVED") -> dict[str, Any]:
        config, enabled = MetaWhatsappService._config(db)
        if not enabled:
            raise MetaWhatsappConfigError("Meta WhatsApp integration is disabled")
        waba_id = str(config.get("waba_id") or "").strip()
        if not waba_id:
            raise MetaWhatsappConfigError("waba_id is required")
        params: dict[str, Any] = {"limit": max(1, min(int(limit or 5), 50))}
        if status:
            params["status"] = status
        payload = MetaWhatsappService._graph_request(
            config=config,
            method="GET",
            path=f"{waba_id}/message_templates",
            params=params,
        )
        rows = payload.get("data") if isinstance(payload.get("data"), list) else []
        return {"ok": True, "templates": rows, "count": len(rows)}

    @staticmethod
    def send_template(
        db: Session,
        *,
        to_number: str,
        template_name: str,
        template_language: str,
    ) -> dict[str, Any]:
        config, enabled = MetaWhatsappService._config(db)
        if not enabled:
            raise MetaWhatsappConfigError("Meta WhatsApp integration is disabled")
        phone_number_id = str(config.get("phone_number_id") or "").strip()
        recipient = re.sub(r"\D", "", str(to_number or "").strip())
        name = str(template_name or "").strip()
        language = str(template_language or "").strip()
        if not phone_number_id:
            raise MetaWhatsappConfigError("phone_number_id is required")
        if not recipient:
            raise MetaWhatsappConfigError("to_number is required")
        if not name:
            raise MetaWhatsappConfigError("template_name is required")
        if not language:
            raise MetaWhatsappConfigError("template_language is required")
        body = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "template",
            "template": {"name": name, "language": {"code": language}},
        }
        payload = MetaWhatsappService._graph_request(
            config=config,
            method="POST",
            path=f"{phone_number_id}/messages",
            json_body=body,
        )
        message_id = None
        messages = payload.get("messages")
        if isinstance(messages, list) and messages:
            message_id = str((messages[0] or {}).get("id") or "").strip() or None
        return {
            "ok": True,
            "message_id": message_id,
            "phone_number_id": phone_number_id,
            "to": recipient,
            "template_name": name,
            "template_language": language,
            "response": payload,
        }

    @staticmethod
    def _normalize_recipient(to_number: str) -> str:
        digits = re.sub(r"\D", "", str(to_number or "").strip())
        if not digits:
            return ""
        return digits

    @staticmethod
    def _normalize_language_code(raw: str | None) -> str:
        text = str(raw or "en_US").strip() or "en_US"
        normalized = text.replace("-", "_")
        if "_" in normalized:
            parts = normalized.split("_", 1)
            return f"{parts[0].lower()}_{parts[1].upper()}"
        return normalized.lower()

    @staticmethod
    def _resolve_template_name(
        db: Session,
        *,
        template_name: str | None,
        template_id: str | None,
    ) -> str | None:
        resolved_name, resolved_id = TelnyxMessagingService.resolve_whatsapp_template_ref(
            template_name=template_name,
            template_id=template_id,
        )
        if resolved_name:
            return resolved_name
        lookup_id = str(resolved_id or template_id or "").strip()
        if not lookup_id:
            return None
        if lookup_id.startswith(_META_RECORD_PREFIX):
            lookup_id = lookup_id[len(_META_RECORD_PREFIX) :]
        row = db.execute(
            select(TelnyxWhatsappTemplate)
            .where(
                (TelnyxWhatsappTemplate.telnyx_record_id == lookup_id)
                | (TelnyxWhatsappTemplate.telnyx_record_id == f"{_META_RECORD_PREFIX}{lookup_id}")
                | (TelnyxWhatsappTemplate.template_id == lookup_id)
                | (TelnyxWhatsappTemplate.name == lookup_id)
            )
            .order_by(TelnyxWhatsappTemplate.updated_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row is not None:
            return str(row.name or "").strip() or None
        return None

    @staticmethod
    def fetch_all_templates(db: Session) -> list[dict[str, Any]]:
        config, enabled = MetaWhatsappService._config(db)
        if not enabled:
            raise MetaWhatsappConfigError("Meta WhatsApp integration is disabled")
        waba_id = str(config.get("waba_id") or "").strip()
        if not waba_id:
            raise MetaWhatsappConfigError("waba_id is required")
        rows: list[dict[str, Any]] = []
        after: str | None = None
        # Explicit fields — without `components`, body_preview is wiped and the dashboard
        # shows Meta template names instead of question text.
        fields = "id,name,language,status,category,components,rejected_reason"
        while True:
            params: dict[str, Any] = {"limit": 250, "fields": fields}
            if after:
                params["after"] = after
            payload = MetaWhatsappService._graph_request(
                config=config,
                method="GET",
                path=f"{waba_id}/message_templates",
                params=params,
            )
            chunk = payload.get("data") if isinstance(payload.get("data"), list) else []
            rows.extend(item for item in chunk if isinstance(item, dict))
            paging = payload.get("paging") if isinstance(payload.get("paging"), dict) else {}
            cursors = paging.get("cursors") if isinstance(paging.get("cursors"), dict) else {}
            after = str(cursors.get("after") or "").strip() or None
            if not after or not paging.get("next"):
                break
        return rows

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
        messaging_profile_id: str | None = None,
    ) -> TelnyxMessageResult:
        del messaging_profile_id  # Meta uses phone_number_id from config
        config, enabled = MetaWhatsappService._config(db)
        if not enabled:
            return TelnyxMessageResult(
                ok=False,
                status="disabled",
                detail="Meta WhatsApp integration is disabled",
                channel="whatsapp",
            )
        phone_number_id = str(config.get("phone_number_id") or "").strip()
        if not phone_number_id:
            return TelnyxMessageResult(
                ok=False,
                status="not_configured",
                detail="Meta phone_number_id is not configured",
                channel="whatsapp",
            )
        recipient = MetaWhatsappService._normalize_recipient(to_number)
        if not recipient:
            return TelnyxMessageResult(ok=False, status="invalid_to", detail="Recipient phone number is invalid.", channel="whatsapp")

        sender_raw = str(from_number or config.get("whatsapp_from") or "").strip()
        try:
            sender = normalize_e164(sender_raw) if sender_raw else ""
        except ValueError:
            sender = sender_raw

        resolved_name = MetaWhatsappService._resolve_template_name(
            db,
            template_name=template_name,
            template_id=template_id,
        )
        lang = MetaWhatsappService._normalize_language_code(template_language)

        message_body: dict[str, Any]
        if resolved_name or template_name or template_id:
            name = resolved_name or str(template_name or "").strip()
            if not name:
                return TelnyxMessageResult(
                    ok=False,
                    status="invalid_payload",
                    detail="WhatsApp template name could not be resolved for Meta send.",
                    channel="whatsapp",
                )
            template: dict[str, Any] = {
                "name": name,
                "language": {"code": lang},
            }
            if template_components:
                template["components"] = template_components
            message_body = {
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "template",
                "template": template,
            }
        else:
            text_body = str(body or "").strip()
            if not text_body:
                return TelnyxMessageResult(
                    ok=False,
                    status="invalid_payload",
                    detail="WhatsApp message body is required unless a template is provided.",
                    channel="whatsapp",
                )
            message_body = {
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "text",
                "text": {"body": text_body},
            }

        from app.services.wa_send_rate_limit import acquire_whatsapp_send_slot

        acquire_whatsapp_send_slot(block=True)
        try:
            payload = MetaWhatsappService._graph_request(
                config=config,
                method="POST",
                path=f"{phone_number_id}/messages",
                json_body=message_body,
            )
        except MetaWhatsappConfigError as exc:
            return TelnyxMessageResult(ok=False, status="not_configured", detail=str(exc), channel="whatsapp")
        except MetaWhatsappServiceError as exc:
            logger.error("meta_whatsapp_send_failed to=%s detail=%s", recipient, exc)
            return TelnyxMessageResult(ok=False, status="http_error", detail=str(exc), channel="whatsapp")

        message_id = None
        messages = payload.get("messages")
        if isinstance(messages, list) and messages:
            message_id = str((messages[0] or {}).get("id") or "").strip() or None

        rendered_body = str(body or "").strip() or (f"template:{resolved_name or template_name}" if (resolved_name or template_name) else "")
        if org_id:
            try:
                LogService.create_whatsapp_log(
                    db,
                    org_id=org_id,
                    direction="outbound",
                    from_number=sender or normalize_e164(str(config.get("whatsapp_from") or "")),
                    to_number=normalize_e164(f"+{recipient}") if recipient else to_number,
                    body=rendered_body,
                    status="sent",
                    external_message_id=message_id,
                    provider="meta_whatsapp",
                    raw_payload=json.dumps(payload, ensure_ascii=False),
                )
            except Exception:
                logger.exception("meta_whatsapp_outbound_log_failed to=%s", recipient)

        if message_id and org_id and meter_usage:
            try:
                from app.services.usage_wallet_service import UsageWalletService

                UsageWalletService.record_whatsapp_usage(db, org_id=org_id, units=1)
            except Exception:
                pass

        return TelnyxMessageResult(
            ok=True,
            status="sent",
            external_id=message_id,
            channel="whatsapp",
            payload=payload if isinstance(payload, dict) else None,
        )
