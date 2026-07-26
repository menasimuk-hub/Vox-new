"""Best-effort WhatsApp ping to the exhibitor's notify_mobile when an Expo lead scores 'hot'.

A missed notification must never block session completion — every failure is logged and
swallowed rather than raised.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.expo import ExpoBooth, ExpoLead

logger = logging.getLogger(__name__)


def _format_alert(lead: ExpoLead) -> str:
    name = str(lead.name or "A visitor").strip() or "A visitor"
    company = f" from {lead.company}" if lead.company else ""
    contact = str(lead.visitor_phone or lead.visitor_email or "").strip() or "no contact on file"
    interest = str(lead.interest or "").strip()
    lines = [f"🔥 Hot lead: {name}{company} — {contact}"]
    if interest:
        lines.append(f"Interested in: {interest[:200]}")
    return "\n".join(lines)


def notify_hot_lead(db: Session, *, booth: ExpoBooth, lead: ExpoLead) -> bool:
    """Send a best-effort WhatsApp alert to the exhibitor's notify_mobile. Never raises."""
    to_number = str(getattr(booth, "notify_mobile", None) or "").strip()
    if not to_number:
        return False
    try:
        from app.services.telnyx_messaging_service import TelnyxMessagingService

        result = TelnyxMessagingService.send_whatsapp(
            db,
            to_number=to_number,
            body=_format_alert(lead),
            org_id=booth.org_id,
            meter_usage=False,
            service_code="expo",
        )
        return bool(result.ok)
    except Exception:
        logger.exception("expo_hot_lead_notify_failed booth=%s lead=%s", booth.id, lead.id)
        return False
