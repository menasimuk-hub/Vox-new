"""Send sales WhatsApp via approved Telnyx/Meta templates (with plain-text fallback)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.sales_whatsapp_telnyx_service import (
    TELNYX_SALES_TEMPLATE_LANGUAGE,
    build_telnyx_components,
    telnyx_template_name,
)
from app.services.telnyx_messaging_service import TelnyxMessageResult, TelnyxMessagingService


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

    if use_meta_template and meta_name:
        result = TelnyxMessagingService.send_whatsapp(
            db,
            to_number=to_number,
            body=body,
            template_name=meta_name,
            template_language=TELNYX_SALES_TEMPLATE_LANGUAGE,
            template_components=components,
            org_id=None,
            meter_usage=False,
        )
        if result.ok:
            return result

    return TelnyxMessagingService.send_whatsapp(
        db,
        to_number=to_number,
        body=body,
        org_id=None,
        meter_usage=False,
    )
