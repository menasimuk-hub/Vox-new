from __future__ import annotations

import logging
import re
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.services.meta_whatsapp_config_service import MetaWhatsappConfigError, graph_api_base, validate_meta_whatsapp_config
from app.services.provider_settings import ProviderSettingsService

logger = logging.getLogger(__name__)


class MetaWhatsappServiceError(RuntimeError):
    pass


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
            raise MetaWhatsappServiceError(f"Meta Graph API error ({code}): {detail}")
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
