"""Central PECR STOP / opt-out keyword handling (survey and interview stay separate)."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.messaging_log_service import normalize_e164
from app.services.org_opt_out_service import OrgOptOutService
from app.services.telnyx_messaging_service import TelnyxMessagingService
from app.services.uk_compliance_audit_service import UkComplianceAuditService

logger = logging.getLogger(__name__)

# Meta / PECR standard keywords — never treat as survey answers or interview booking intents.
PECR_STOP_RE = re.compile(
    r"^\s*(STOP|STOPALL|UNSUBSCRIBE|CANCEL|END|QUIT)\s*\.?\s*$",
    re.IGNORECASE,
)

INTERVIEW_OPT_OUT_CONFIRM = (
    "You have been unsubscribed from further messages from this organisation. "
    "Reply START if this was a mistake."
)


def is_pecr_stop_message(body: str) -> bool:
    return bool(PECR_STOP_RE.match(str(body or "").strip()))


def handle_interview_wa_pecr_opt_out(
    db: Session,
    *,
    org_id: str,
    phone_e164: str,
    source: str = "interview_wa_inbound",
) -> dict[str, Any] | None:
    """Org-level suppression for interview WA — does not touch survey recipient state."""
    phone = normalize_e164(phone_e164)
    if not phone or not org_id:
        return None
    OrgOptOutService.add_opt_out(db, org_id=org_id, phone=phone, reason=source)
    UkComplianceAuditService.record(
        db,
        event_type="opt_out.received",
        org_id=org_id,
        detail={"channel": "whatsapp", "workflow": "interview", "phone": phone, "source": source},
    )
    confirm = INTERVIEW_OPT_OUT_CONFIRM
    try:
        TelnyxMessagingService.send_whatsapp(db, to=phone, body=confirm)
    except Exception as exc:
        logger.warning("interview_wa_opt_out_confirm_failed", extra={"org_id": org_id, "error": str(exc)})
    return {"handled": True, "action": "opt_out", "workflow": "interview"}


def should_block_outbound_phone(db: Session, *, org_id: str, phone_e164: str | None) -> str | None:
    """Return skip reason if org suppression list blocks send."""
    phone = normalize_e164(phone_e164 or "")
    if not phone:
        return "missing_phone"
    if OrgOptOutService.is_phone_opted_out(db, org_id=org_id, phone=phone):
        return "org_opt_out"
    return None
