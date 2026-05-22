"""Send sales WhatsApp via approved Telnyx/Meta templates (with plain-text fallback)."""

from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.services.sales_whatsapp_telnyx_service import (
    build_telnyx_components,
    resolve_whatsapp_template_languages,
    telnyx_template_name,
)
from app.services.telnyx_messaging_service import TelnyxMessageResult, TelnyxMessagingService
from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService

logger = logging.getLogger(__name__)

_LANGUAGE_ERROR_RE = re.compile(
    r"translation|language|locale|template.*not found|does not exist",
    re.I,
)


def _should_retry_language(result: TelnyxMessageResult) -> bool:
    if result.ok:
        return False
    detail = str(result.detail or result.status or "")
    return bool(_LANGUAGE_ERROR_RE.search(detail))


def send_sales_whatsapp(
    db: Session,
    *,
    to_number: str,
    template_key: str | None,
    body: str,
    variables: dict[str, str] | None = None,
    use_meta_template: bool = True,
) -> TelnyxMessageResult:
    meta_name = telnyx_template_name(template_key or "") if template_key else None
    components = build_telnyx_components(template_key, variables or {}) if template_key and variables else None

    if use_meta_template and template_key:
        synced = TelnyxWhatsappTemplateSyncService.get_for_sales_key(db, template_key)
        if synced and synced.template_id and str(synced.status or "").upper() == "APPROVED":
            send_components = TelnyxWhatsappTemplateSyncService.build_components_for_row(synced, variables=variables)
            result = TelnyxMessagingService.send_whatsapp(
                db,
                to_number=to_number,
                body=body,
                template_id=synced.template_id,
                template_language=synced.language,
                template_components=send_components or components,
                org_id=None,
                meter_usage=False,
            )
            if result.ok:
                return result
            logger.warning(
                "sales_whatsapp_synced_template_send_failed",
                extra={
                    "template_id": synced.template_id,
                    "name": synced.name,
                    "detail": result.detail or result.status,
                },
            )

    if use_meta_template and meta_name:
        last_result: TelnyxMessageResult | None = None
        for lang in resolve_whatsapp_template_languages(db):
            result = TelnyxMessagingService.send_whatsapp(
                db,
                to_number=to_number,
                body=body,
                template_name=meta_name,
                template_language=lang,
                template_components=components,
                org_id=None,
                meter_usage=False,
            )
            if result.ok:
                if lang != resolve_whatsapp_template_languages(db)[0]:
                    logger.info(
                        "sales_whatsapp_template_language_fallback",
                        extra={"template": meta_name, "language": lang},
                    )
                return result
            last_result = result
            logger.warning(
                "sales_whatsapp_template_send_failed",
                extra={
                    "template": meta_name,
                    "language": lang,
                    "detail": result.detail or result.status,
                },
            )
            if not _should_retry_language(result):
                break

        detail = (last_result.detail or last_result.status if last_result else "unknown error")
        hint = "Sync templates under Admin → Integrations → Telnyx (Sync WhatsApp templates)."
        return TelnyxMessageResult(
            ok=False,
            status="template_failed",
            detail=(
                f"WhatsApp template '{meta_name}' failed: {detail}. "
                f"{hint} Confirm template is APPROVED in Telnyx (en_US)."
            ),
            channel="whatsapp",
        )

    return TelnyxMessagingService.send_whatsapp(
        db,
        to_number=to_number,
        body=body,
        org_id=None,
        meter_usage=False,
    )
