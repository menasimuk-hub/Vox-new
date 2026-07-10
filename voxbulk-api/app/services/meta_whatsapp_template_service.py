"""Meta Graph API — WhatsApp message template create/delete/fetch (zero Telnyx for templates)."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.services.meta_whatsapp_config_service import MetaWhatsappConfigError
from app.services.meta_whatsapp_service import MetaWhatsappService, MetaWhatsappServiceError, _META_RECORD_PREFIX
from app.services.telnyx_whatsapp_template_sync_service import _normalize_meta_template_item
from app.services.whatsapp_provider_service import is_meta_whatsapp_primary
from app.services.wa_template_meta_sync import enrich_template_push_error_payload, parse_meta_error_from_provider_detail

logger = logging.getLogger(__name__)


class MetaWhatsappTemplateError(RuntimeError):
    def __init__(self, message: str, *, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.payload = payload


def require_meta_whatsapp_primary(
    db: Session,
    *,
    service_code: str | None = "survey",
    connection_profile_id: str | None = None,
) -> dict[str, Any]:
    if connection_profile_id:
        from app.services.connection.config_resolver import (
            WhatsappSyncRouteError,
            resolve_whatsapp_route_by_profile_id,
        )

        try:
            route = resolve_whatsapp_route_by_profile_id(
                db, connection_profile_id, service_code=service_code or "survey"
            )
        except WhatsappSyncRouteError as exc:
            raise MetaWhatsappTemplateError(str(exc)) from exc
        if not route.is_meta:
            raise MetaWhatsappTemplateError(
                f"Connection profile uses {route.provider}, not Meta — cannot push to Meta API."
            )
        return route.config

    if not is_meta_whatsapp_primary(db, service_code=service_code):
        raise MetaWhatsappTemplateError(
            "Meta WhatsApp is not configured. Open Admin → Integrations → Meta WhatsApp, "
            "enable the integration, and save WABA id, phone number id, and access token."
        )
    config, _enabled = MetaWhatsappService._config(db, service_code=service_code)
    return config


def _meta_http_error_detail(exc: httpx.HTTPStatusError) -> str:
    try:
        body = exc.response.json()
    except ValueError:
        return exc.response.text[:2000]
    err = body.get("error") if isinstance(body, dict) else None
    if isinstance(err, dict):
        return json.dumps({"error": err}, ensure_ascii=False)[:2000]
    return str(body)[:2000]


def _graph_error_as_provider_detail(exc: Exception) -> str:
    if isinstance(exc, MetaWhatsappServiceError):
        if exc.error_payload:
            return f"meta api error: {json.dumps({'error': exc.error_payload}, ensure_ascii=False)}"
        return f"meta api error: {json.dumps({'error': {'message': str(exc)}}, ensure_ascii=False)}"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"meta api error: {_meta_http_error_detail(exc)}"
    return str(exc)


def _meta_template_error_from_service_exc(
    exc: MetaWhatsappServiceError,
    *,
    template_name: str,
    language: str,
) -> MetaWhatsappTemplateError:
    provider_detail = _graph_error_as_provider_detail(exc)
    payload = enrich_template_push_error_payload(
        message=f"Push to Meta failed for “{template_name}”.",
        template_name=template_name,
        language=language,
        provider_error=provider_detail,
        status_code=None,
        telnyx_request_mode="create_or_update_template",
    )
    meta = parse_meta_error_from_provider_detail(provider_detail)
    if meta.get("kind"):
        payload["meta_error_kind"] = meta.get("kind")
    message = str(payload.get("admin_guidance") or payload.get("message") or str(exc))
    subcode = payload.get("meta_error_subcode")
    if subcode and f"subcode={subcode}" not in message:
        message = f"{message} (subcode={subcode})"
    return MetaWhatsappTemplateError(message, payload=payload)


class MetaWhatsappTemplateService:
    @staticmethod
    def create_message_template(
        db: Session,
        *,
        name: str,
        language: str,
        category: str,
        components: list[Any],
        connection_profile_id: str | None = None,
        service_code: str | None = "survey",
    ) -> dict[str, Any]:
        config = require_meta_whatsapp_primary(
            db,
            service_code=service_code,
            connection_profile_id=connection_profile_id,
        )
        waba_id = str(config.get("waba_id") or "").strip()
        payload = {
            "name": str(name or "").strip(),
            "language": MetaWhatsappService._normalize_language_code(language),
            "category": str(category or "UTILITY").strip().upper(),
            "components": components,
        }
        try:
            body = MetaWhatsappService._graph_request(
                config=config,
                method="POST",
                path=f"{waba_id}/message_templates",
                json_body=payload,
                timeout=45.0,
            )
        except MetaWhatsappConfigError as exc:
            raise MetaWhatsappTemplateError(str(exc)) from exc
        except MetaWhatsappServiceError as exc:
            raise _meta_template_error_from_service_exc(
                exc,
                template_name=str(name or ""),
                language=str(language or ""),
            ) from exc
        meta_id = str(body.get("id") or "").strip()
        status = str(body.get("status") or "PENDING").strip().upper()
        return _normalize_meta_template_item(
            {
                "id": meta_id,
                "name": payload["name"],
                "language": payload["language"],
                "category": payload["category"],
                "status": status,
                "components": components,
            },
            waba_id=waba_id,
        )

    @staticmethod
    def update_message_template(
        db: Session,
        *,
        template_id: str,
        components: list[Any],
        category: str | None = None,
        template_name: str | None = None,
        connection_profile_id: str | None = None,
        service_code: str | None = "survey",
    ) -> dict[str, Any]:
        """Edit an existing Meta template in place (same name) — status returns to PENDING for re-review."""
        config = require_meta_whatsapp_primary(
            db,
            service_code=service_code,
            connection_profile_id=connection_profile_id,
        )
        waba_id = str(config.get("waba_id") or "").strip()
        raw_id = str(template_id or "").strip()
        if raw_id.startswith(_META_RECORD_PREFIX):
            raw_id = raw_id[len(_META_RECORD_PREFIX) :]
        if not raw_id:
            raise MetaWhatsappTemplateError("Meta template id is required for update")
        payload: dict[str, Any] = {"components": components}
        if category:
            payload["category"] = str(category or "UTILITY").strip().upper()
        try:
            body = MetaWhatsappService._graph_request(
                config=config,
                method="POST",
                path=raw_id,
                json_body=payload,
                timeout=45.0,
            )
        except MetaWhatsappConfigError as exc:
            raise MetaWhatsappTemplateError(str(exc)) from exc
        except MetaWhatsappServiceError as exc:
            raise _meta_template_error_from_service_exc(
                exc,
                template_name=str(template_name or raw_id),
                language="",
            ) from exc
        meta_id = str(body.get("id") or raw_id).strip()
        status = str(body.get("status") or "PENDING").strip().upper()
        name = str(body.get("name") or "").strip()
        language = MetaWhatsappService._normalize_language_code(str(body.get("language") or "en_US"))
        cat = str(body.get("category") or category or "UTILITY").strip().upper()
        return _normalize_meta_template_item(
            {
                "id": meta_id,
                "name": name,
                "language": language,
                "category": cat,
                "status": status,
                "components": components,
            },
            waba_id=waba_id,
        )

    @staticmethod
    def delete_message_template(
        db: Session,
        *,
        name: str | None = None,
        hsm_id: str | None = None,
        service_code: str | None = "survey",
        connection_profile_id: str | None = None,
    ) -> None:
        config = require_meta_whatsapp_primary(
            db,
            service_code=service_code,
            connection_profile_id=connection_profile_id,
        )
        waba_id = str(config.get("waba_id") or "").strip()
        params: dict[str, Any] = {}
        clean_name = str(name or "").strip() or None
        clean_hsm = None
        if hsm_id:
            raw = str(hsm_id).strip()
            if raw.startswith(_META_RECORD_PREFIX):
                raw = raw[len(_META_RECORD_PREFIX) :]
            clean_hsm = raw or None
        # Meta requires name together with hsm_id when deleting a specific language/id.
        # Name-only deletes all languages for that template name.
        if clean_hsm and clean_name:
            params["hsm_id"] = clean_hsm
            params["name"] = clean_name
        elif clean_name:
            params["name"] = clean_name
        elif clean_hsm:
            params["hsm_id"] = clean_hsm
        else:
            raise MetaWhatsappTemplateError("Template name or hsm_id is required for Meta delete")
        try:
            MetaWhatsappService._graph_request(
                config=config,
                method="DELETE",
                path=f"{waba_id}/message_templates",
                params=params,
                timeout=30.0,
            )
        except MetaWhatsappServiceError as exc:
            if "404" in str(exc) or "not found" in str(exc).lower():
                return
            raise MetaWhatsappTemplateError(str(exc)) from exc

    @staticmethod
    def find_template(
        db: Session,
        *,
        name: str,
        language: str | None = None,
        remote_items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        name_lower = str(name or "").strip().lower()
        if not name_lower:
            return None
        items = remote_items if remote_items is not None else MetaWhatsappService.fetch_all_templates(db)
        lang = MetaWhatsappService._normalize_language_code(language) if language else None
        matches = [
            item
            for item in items
            if isinstance(item, dict) and str(item.get("name") or "").strip().lower() == name_lower
        ]
        if lang:
            exact = [
                m
                for m in matches
                if MetaWhatsappService._normalize_language_code(str(m.get("language") or "")) == lang
            ]
            if exact:
                matches = exact
        if not matches:
            return None
        config, _ = MetaWhatsappService._config(db)
        waba_id = str(config.get("waba_id") or "").strip()
        best = matches[0]
        return _normalize_meta_template_item(best, waba_id=waba_id or None)

    @staticmethod
    def fetch_by_record_id(db: Session, record_id: str) -> dict[str, Any]:
        rid = str(record_id or "").strip()
        if not rid:
            raise MetaWhatsappTemplateError("Meta template record id is required")
        meta_id = rid[len(_META_RECORD_PREFIX) :] if rid.startswith(_META_RECORD_PREFIX) else rid
        items = MetaWhatsappService.fetch_all_templates(db)
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("id") or "").strip() == meta_id:
                config, _ = MetaWhatsappService._config(db)
                waba_id = str(config.get("waba_id") or "").strip()
                return _normalize_meta_template_item(item, waba_id=waba_id or None)
        raise MetaWhatsappTemplateError(f"Meta template not found for id {record_id}")

    @staticmethod
    def push_template_payload(
        db: Session,
        *,
        name: str,
        language: str,
        category: str,
        components: list[Any],
        connection_profile_id: str | None = None,
        service_code: str | None = "survey",
    ) -> dict[str, Any]:
        """Create template on Meta WABA; enrich errors for admin UI."""
        try:
            return MetaWhatsappTemplateService.create_message_template(
                db,
                name=name,
                language=language,
                category=category,
                components=components,
                connection_profile_id=connection_profile_id,
                service_code=service_code,
            )
        except MetaWhatsappTemplateError:
            raise
        except httpx.HTTPStatusError as exc:
            detail = _meta_http_error_detail(exc)
            payload = enrich_template_push_error_payload(
                message=f"Push to Meta failed for “{name}”.",
                template_name=name,
                language=language,
                provider_error=_graph_error_as_provider_detail(exc),
                status_code=exc.response.status_code if exc.response is not None else None,
                telnyx_request_mode="create_or_update_template",
            )
            raise MetaWhatsappTemplateError(
                str(payload.get("admin_guidance") or payload.get("message") or detail),
                payload=payload,
            ) from exc
        except Exception as exc:
            detail = _graph_error_as_provider_detail(exc)
            meta = parse_meta_error_from_provider_detail(detail)
            payload = enrich_template_push_error_payload(
                message=f"Push to Meta failed for “{name}”.",
                template_name=name,
                language=language,
                provider_error=detail,
                status_code=None,
                telnyx_request_mode="create_or_update_template",
            )
            if meta.get("kind"):
                payload["meta_error_kind"] = meta.get("kind")
            raise MetaWhatsappTemplateError(
                str(payload.get("admin_guidance") or payload.get("message") or str(exc)),
                payload=payload,
            ) from exc
