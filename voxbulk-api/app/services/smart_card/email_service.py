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
VISITOR_CATALOGUE_TEMPLATE = "smart_card_visitor_catalogue"
INVITE_TEMPLATE = "smart_card_rep_invite"
MEMBER_INVITE_TEMPLATE = "smart_card_rep_member_invite"
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
        from app.services.platform_sender_email_service import PlatformSenderEmailService

        outbound = PlatformSenderEmailService.resolve_outbound(db, "smart_card")
        if outbound and outbound.get("from_email"):
            return {
                "from_name": outbound.get("from_name"),
                "from_email": outbound.get("from_email"),
                "smtp_username": outbound.get("smtp_username") or outbound.get("from_email"),
                "smtp_password": outbound.get("smtp_password"),
            }
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
    def send_visitor_catalogue(
        db: Session,
        *,
        rep: SmartCardRepresentative,
        lead: SmartCardLead,
        assets: list[dict[str, Any]],
    ) -> bool:
        """Email the visitor the products they picked — files attached plus download links."""
        to_email = (lead.visitor_email or "").strip()
        if not to_email or not assets:
            return False

        from app.services.smart_card.asset_delivery_service import email_attachments

        links_html = "".join(
            f'<p><a href="{a.get("url")}">{a.get("title") or "Download"}</a></p>'
            for a in assets
            if a.get("url")
        )
        list_text = "\n".join(
            f"- {a.get('title') or 'Document'}: {a.get('url')}" for a in assets if a.get("url")
        )
        attachments = email_attachments(assets)
        smtp = SmartCardEmailService._smtp(db)
        variables = {
            "visitor_name": (lead.name or "there").split()[0] if lead.name else "there",
            "rep_name": rep.name or "our team",
            "asset_links": links_html,
            "asset_list": list_text,
        }
        ok, error = TransactionalEmailService.send_templated_optional(
            db,
            template_key=VISITOR_CATALOGUE_TEMPLATE,
            to_email=to_email,
            variables=variables,
            attachments=attachments or None,
            from_email=smtp["from_email"],
            from_name=smtp["from_name"],
            smtp_username=smtp["smtp_username"],
            smtp_password=smtp["smtp_password"],
        )
        if not ok:
            logger.warning("smart_card_visitor_catalogue_email_failed lead=%s err=%s", lead.id, error)
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
        """Legacy invite template (view leads). Prefer send_rep_member_invite for new invites."""
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
    def send_rep_member_invite(
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
        ok, err = TransactionalEmailService.send_templated_optional(
            db,
            template_key=MEMBER_INVITE_TEMPLATE,
            to_email=to_email,
            variables=variables,
            from_email=smtp["from_email"],
            from_name=smtp["from_name"],
            smtp_username=smtp["smtp_username"],
            smtp_password=smtp["smtp_password"],
        )
        if not ok:
            logger.warning("smart_card_rep_member_invite_failed to=%s err=%s", to_email, err)
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
