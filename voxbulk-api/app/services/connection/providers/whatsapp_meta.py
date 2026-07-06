from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.meta_whatsapp_service import MetaWhatsappService
from app.services.telnyx_messaging_service import TelnyxMessageResult


class WhatsappMetaProvider:
    @staticmethod
    def send(
        db: Session,
        *,
        config: dict[str, Any],
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
        return MetaWhatsappService.send_whatsapp_with_config(
            db,
            config=config,
            to_number=to_number,
            body=body,
            from_number=from_number,
            template_name=template_name,
            template_id=template_id,
            template_language=template_language,
            template_components=template_components,
            org_id=org_id,
            meter_usage=meter_usage,
        )
