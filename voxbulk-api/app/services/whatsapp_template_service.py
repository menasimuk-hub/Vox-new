from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.data.system_whatsapp_defaults import SYSTEM_WHATSAPP_DEFAULTS, WHATSAPP_SYSTEM_TEMPLATE_KEYS
from app.models.whatsapp_template import WhatsAppTemplate
from app.services.channel_template_service import ChannelTemplateService


class WhatsAppTemplateService:
    @staticmethod
    def is_system_key(key: str) -> bool:
        return (key or "").strip().lower() in WHATSAPP_SYSTEM_TEMPLATE_KEYS

    @staticmethod
    def ensure_system_templates(db: Session) -> None:
        for key in WHATSAPP_SYSTEM_TEMPLATE_KEYS:
            if ChannelTemplateService.get(db, model=WhatsAppTemplate, key=key) is not None:
                continue
            defaults = SYSTEM_WHATSAPP_DEFAULTS.get(key, {})
            ChannelTemplateService.create(
                db,
                model=WhatsAppTemplate,
                key=key,
                name=defaults.get("name") or key.replace("_", " ").title(),
                body=defaults.get("body") or "",
                is_enabled=True,
            )

    @staticmethod
    def list_all(db: Session) -> list[dict[str, Any]]:
        WhatsAppTemplateService.ensure_system_templates(db)
        rows = ChannelTemplateService.list_all(db, model=WhatsAppTemplate)
        for row in rows:
            row["is_system"] = WhatsAppTemplateService.is_system_key(row.get("template_key") or "")
        return rows

    @staticmethod
    def render_body(db: Session, *, template_key: str, variables: dict[str, str], fallback: str) -> str:
        from app.services.transactional_email_service import substitute_placeholders

        row = ChannelTemplateService.get(db, model=WhatsAppTemplate, key=template_key)
        if row is None or not row.is_enabled:
            return substitute_placeholders(fallback, variables).strip()
        body = str(row.body or "").strip()
        if not body:
            return substitute_placeholders(fallback, variables).strip()
        return substitute_placeholders(body, variables).strip()
