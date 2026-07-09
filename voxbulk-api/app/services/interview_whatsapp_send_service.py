"""Send interview WhatsApp via Meta/Telnyx templates with language retry and plain fallback."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.sales_whatsapp_telnyx_service import resolve_whatsapp_template_languages
from app.services.telnyx_messaging_service import TelnyxMessageResult, TelnyxMessagingService
from app.services.telnyx_whatsapp_template_sync_service import send_template_id_for_row
from app.services.wa_template_profile_push_service import WaTemplateProfilePushService

logger = logging.getLogger(__name__)

_LANGUAGE_ERROR_RE = re.compile(
    r"translation|language|locale|template.*not found|does not exist|132001",
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


class InterviewWhatsappSendService:
    @staticmethod
    def send_template_or_plain(
        db: Session,
        *,
        to_number: str,
        body: str,
        org_id: str | None,
        template_row: TelnyxWhatsappTemplate | None = None,
        template_name: str | None = None,
        template_id: str | None = None,
        template_language: str | None = None,
        template_components: list[dict[str, Any]] | None = None,
        require_template: bool = False,
        service_code: str = "ai_interview",
    ) -> TelnyxMessageResult:
        """Try Meta/Telnyx HSM with language retries; fall back to plain session text."""
        row = template_row
        name = str(template_name or (row.name if row else "") or "").strip()
        primary_lang = str(template_language or (row.language if row else None) or "").strip()
        components = template_components
        send_id = str(template_id or "").strip()
        if row is not None and not send_id:
            send_id = WaTemplateProfilePushService.send_template_id_for_active_profile(
                db,
                row,
                org_id=org_id,
                service_code=service_code,
            ) or send_template_id_for_row(row)

        last_result: TelnyxMessageResult | None = None
        if name or send_id:
            langs = _language_attempt_order(db, primary_lang or None)
            for lang in langs:
                kwargs: dict[str, Any] = {
                    "to_number": to_number,
                    "body": body,
                    "template_language": lang,
                    "template_components": components,
                    "org_id": org_id,
                    "meter_usage": False,
                    "service_code": service_code,
                }
                if name:
                    kwargs["template_name"] = name
                if send_id:
                    kwargs["template_id"] = send_id
                attempt = TelnyxMessagingService.send_whatsapp(db, **kwargs)
                last_result = attempt
                if attempt.ok:
                    if lang != (primary_lang or langs[0]):
                        logger.info(
                            "interview_wa_template_language_fallback",
                            extra={"template": name or send_id, "language": lang},
                        )
                    return attempt
                logger.warning(
                    "interview_wa_template_send_failed",
                    extra={
                        "template": name or send_id,
                        "language": lang,
                        "detail": attempt.detail or attempt.status,
                    },
                )
                if not _should_retry_language(attempt):
                    break

        if require_template and (name or send_id):
            detail = (last_result.detail or last_result.status if last_result else "unknown error")
            return TelnyxMessageResult(
                ok=False,
                status="template_failed",
                detail=f"WhatsApp template failed: {detail}",
                channel="whatsapp",
            )

        if row is None and not name and not send_id:
            if require_template:
                return TelnyxMessageResult(
                    ok=False,
                    status="missing_template",
                    detail="No approved WhatsApp interview template matched this step.",
                    channel="whatsapp",
                )

        logger.warning(
            "interview_wa_plain_text_fallback to=%s org_id=%s template=%s body=%r",
            to_number,
            org_id,
            name or send_id or "none",
            str(body or "")[:120],
        )
        return TelnyxMessagingService.send_whatsapp(
            db,
            to_number=to_number,
            body=body,
            org_id=org_id,
            meter_usage=False,
            service_code=service_code,
        )
