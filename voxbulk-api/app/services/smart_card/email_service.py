"""Smart Card QR emails via smartqr@voxbulk.com mailbox."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.smart_card import SmartCardLead, SmartCardRepresentative
from app.services.smart_card.mailbox_settings_service import SmartCardMailboxSettingsService
from app.services.transactional_email_service import TransactionalEmailService

logger = logging.getLogger(__name__)

LEAD_TEMPLATE = "smart_card_lead_notify"
INVITE_TEMPLATE = "smart_card_rep_invite"
RENEWAL_TEMPLATES = {
    "30d": "smart_card_renewal_reminder_30d",
    "14d": "smart_card_renewal_reminder_14d",
    "7d": "smart_card_renewal_reminder_7d",
    "1d": "smart_card_renewal_reminder_1d",
}
EXPIRED_TEMPLATE = "smart_card_expired"


class SmartCardEmailService:
    @staticmethod
    def _smtp(db: Session) -> dict[str, str | None]:
        from_name, from_email = SmartCardMailboxSettingsService.from_address(db)
        row = SmartCardMailboxSettingsService.get_row(db)
        password = SmartCardMailboxSettingsService.get_decrypted_password(db)
        return {
            "from_name": from_name,
            "from_email": from_email,
            "smtp_username": row.smtp_username or from_email,
            "smtp_password": password,
        }

    @staticmethod
    def notify_rep_lead(db: Session, *, rep: SmartCardRepresentative, lead: SmartCardLead) -> bool:
        to_email = (rep.email or "").strip()
        if not to_email:
            return False
        smtp = SmartCardEmailService._smtp(db)
        variables = {
            "rep_name": rep.name or "there",
            "lead_name": lead.name or "—",
            "company": lead.company or "—",
            "mobile": lead.visitor_phone or "—",
            "email": lead.visitor_email or "—",
            "interest": lead.interest or "—",
            "timeline": lead.buying_timeline or "—",
            "lead_score": lead.lead_score or "—",
            "ai_summary": lead.ai_summary or "—",
            "suggested_follow_up": lead.suggested_follow_up or "—",
            "leads_url": "https://dashboard.voxbulk.com/smart-card/leads",
        }
        ok, _ = TransactionalEmailService.send_templated_optional(
            db,
            template_key=LEAD_TEMPLATE,
            to_email=to_email,
            variables=variables,
            from_email=smtp["from_email"],
            from_name=smtp["from_name"],
            smtp_username=smtp["smtp_username"],
            smtp_password=smtp["smtp_password"],
        )
        return bool(ok)

    @staticmethod
    def send_rep_invite(
        db: Session,
        *,
        to_email: str,
        rep_name: str,
        org_name: str,
        signup_url: str,
    ) -> bool:
        smtp = SmartCardEmailService._smtp(db)
        variables = {
            "rep_name": rep_name or "there",
            "org_name": org_name or "your organisation",
            "signup_url": signup_url,
        }
        ok, _ = TransactionalEmailService.send_templated_optional(
            db,
            template_key=INVITE_TEMPLATE,
            to_email=to_email,
            variables=variables,
            from_email=smtp["from_email"],
            from_name=smtp["from_name"],
            smtp_username=smtp["smtp_username"],
            smtp_password=smtp["smtp_password"],
        )
        return bool(ok)

    @staticmethod
    def send_renewal_reminder(
        db: Session,
        *,
        to_email: str,
        window_key: str,
        org_name: str,
        period_end: str,
        seats: int,
    ) -> bool:
        key = RENEWAL_TEMPLATES.get(window_key) or EXPIRED_TEMPLATE
        smtp = SmartCardEmailService._smtp(db)
        variables = {
            "org_name": org_name,
            "period_end": period_end,
            "seats": str(seats),
            "renew_url": "https://dashboard.voxbulk.com/account/smart-card/packages",
            "window_label": window_key,
        }
        ok, _ = TransactionalEmailService.send_templated_optional(
            db,
            template_key=key,
            to_email=to_email,
            variables=variables,
            from_email=smtp["from_email"],
            from_name=smtp["from_name"],
            smtp_username=smtp["smtp_username"],
            smtp_password=smtp["smtp_password"],
        )
        return bool(ok)
