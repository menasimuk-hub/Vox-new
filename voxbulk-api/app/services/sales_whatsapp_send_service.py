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
from app.services.telnyx_whatsapp_template_sync_service import (
    TelnyxWhatsappTemplateSyncService,
    send_template_id_for_row,
)

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


def _language_attempt_order(db: Session, primary: str | None) -> list[str]:
    ordered: list[str] = []
    for candidate in (primary, *resolve_whatsapp_template_languages(db)):
        code = str(candidate or "").strip()
        if code and code not in ordered:
            ordered.append(code)
    return ordered or ["en_US"]


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
    base_components = build_telnyx_components(template_key, variables or {}) if template_key and variables else None
    last_result: TelnyxMessageResult | None = None

    if use_meta_template and template_key:
        synced = TelnyxWhatsappTemplateSyncService.get_for_sales_key(db, template_key)
        if synced and str(synced.status or "").upper() == "APPROVED":
            components = TelnyxWhatsappTemplateSyncService.build_components_for_row(synced, variables=variables) or base_components
            langs = _language_attempt_order(db, synced.language)
            template_name = str(synced.name or meta_name or "").strip()

            for lang in langs:
                if template_name:
                    attempt = TelnyxMessagingService.send_whatsapp(
                        db,
                        to_number=to_number,
                        body=body,
                        template_name=template_name,
                        template_language=lang,
                        template_components=components,
                        org_id=None,
                        meter_usage=False,
                    )
                    last_result = attempt
                    if attempt.ok:
                        return attempt
                    logger.warning(
                        "sales_whatsapp_template_name_send_failed",
                        extra={
                            "template": template_name,
                            "language": lang,
                            "detail": attempt.detail or attempt.status,
                        },
                    )
                    if not _should_retry_language(attempt):
                        break

            send_tid = send_template_id_for_row(synced)
            for lang in langs[:2]:
                attempt = TelnyxMessagingService.send_whatsapp(
                    db,
                    to_number=to_number,
                    body=body,
                    template_id=send_tid,
                    template_language=lang,
                    template_components=components,
                    org_id=None,
                    meter_usage=False,
                )
                last_result = attempt
                if attempt.ok:
                    return attempt
                logger.warning(
                    "sales_whatsapp_synced_template_id_send_failed",
                    extra={
                        "template_id": send_tid,
                        "name": synced.name,
                        "language": lang,
                        "detail": attempt.detail or attempt.status,
                    },
                )
                if not _should_retry_language(attempt):
                    break

    if use_meta_template and meta_name:
        for lang in resolve_whatsapp_template_languages(db):
            result = TelnyxMessagingService.send_whatsapp(
                db,
                to_number=to_number,
                body=body,
                template_name=meta_name,
                template_language=lang,
                template_components=base_components,
                org_id=None,
                meter_usage=False,
            )
            last_result = result
            if result.ok:
                if lang != resolve_whatsapp_template_languages(db)[0]:
                    logger.info(
                        "sales_whatsapp_template_language_fallback",
                        extra={"template": meta_name, "language": lang},
                    )
                return result
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
                f"{hint} Confirm all four voxbulk_sales_* templates are APPROVED and language matches (en_US / en_GB)."
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
