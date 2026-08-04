from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.data.brand_email_layout import cta_button, wrap_brand_email
from app.models.admin_user import AdminUser
from app.models.organisation import Organisation
from app.models.support_ticket import SupportTicket
from app.models.user import User
from app.services.email_template_service import EmailTemplateService
from app.services.smtp_mailer_service import SmtpMailerError, SmtpMailerService
from app.services.support_mailbox_settings_service import SupportMailboxSettingsService
from app.services.transactional_email_service import substitute_placeholders

logger = logging.getLogger(__name__)

SUPPORT_TICKET_CREATED = "support_ticket_created"
SUPPORT_TICKET_REPLY = "support_ticket_reply"
SUPPORT_TICKET_STATUS = "support_ticket_status"
SUPPORT_TICKET_ASSIGNED = "support_ticket_assigned"

SUPPORT_EMAIL_DEFAULTS: dict[str, dict[str, str]] = {
    SUPPORT_TICKET_CREATED: {
        "title": "Support ticket created",
        "subject": "We received your request {{public_ref}}",
        "body": wrap_brand_email(
            title="Support request received",
            inner_html="""<p>Hi <strong>{{customer_name}}</strong>,</p>
  <p>We have opened ticket <strong>{{public_ref}}</strong> for <strong>{{organisation_name}}</strong>.</p>
  <p><strong>Subject:</strong> {{subject}}</p>
  <p>Our team will reply as soon as possible.</p>
  """
            + cta_button(href="{{ticket_url}}", label="View ticket")
            + """
  <p style="font-size:13px;color:#6b6560;">Questions? Contact <a href="mailto:{{support_email}}" style="color:#1a2d5c;">{{support_email}}</a>.</p>""",
            footer="Sent by VOXBULK Support · support@voxbulk.com",
        ),
    },
    SUPPORT_TICKET_REPLY: {
        "title": "Support ticket reply",
        "subject": "Update on {{public_ref}}: {{subject}}",
        "body": wrap_brand_email(
            title="New reply from support",
            inner_html="""<p>Hi <strong>{{customer_name}}</strong>,</p>
  <p>There is a new reply on ticket <strong>{{public_ref}}</strong>.</p>
  <div style="margin:16px 0;padding:14px;border:1px solid #e5e2dc;border-radius:8px;background:#faf9f7;white-space:pre-wrap;">{{reply_body}}</div>
  """
            + cta_button(href="{{ticket_url}}", label="Open ticket")
            + """
  <p style="font-size:13px;color:#6b6560;">Reply from this email thread or in your dashboard.</p>""",
            footer="Sent by VOXBULK Support · support@voxbulk.com",
        ),
    },
    SUPPORT_TICKET_STATUS: {
        "title": "Support ticket status",
        "subject": "Ticket {{public_ref}} is now {{status}}",
        "body": wrap_brand_email(
            title="Ticket status updated",
            inner_html="""<p>Hi <strong>{{customer_name}}</strong>,</p>
  <p>Ticket <strong>{{public_ref}}</strong> ({{subject}}) is now <strong>{{status}}</strong>.</p>
  """
            + cta_button(href="{{ticket_url}}", label="View ticket")
            + """
  <p style="font-size:13px;color:#6b6560;">Need more help? Email <a href="mailto:{{support_email}}" style="color:#1a2d5c;">{{support_email}}</a>.</p>""",
            footer="Sent by VOXBULK Support · support@voxbulk.com",
        ),
    },
    SUPPORT_TICKET_ASSIGNED: {
        "title": "Support ticket assigned",
        "subject": "Assigned: {{public_ref}} — {{subject}}",
        "body": wrap_brand_email(
            title="Ticket assigned to you",
            inner_html="""<p>Hi,</p>
  <p>Ticket <strong>{{public_ref}}</strong> has been assigned to you.</p>
  <p><strong>Org:</strong> {{organisation_name}}<br/><strong>Subject:</strong> {{subject}}<br/><strong>Status:</strong> {{status}}</p>
  """
            + cta_button(href="{{admin_ticket_url}}", label="Open in admin")
            + """
  <p style="font-size:13px;color:#6b6560;">Support Disk · VoxBulk</p>""",
            footer="Sent by VOXBULK Support · support@voxbulk.com",
        ),
    },
}


def register_support_email_defaults() -> None:
    """Merge Support Disk template defaults into SYSTEM_EMAIL_DEFAULTS (insert-missing only)."""
    from app.data import system_email_defaults as sed

    for key, value in SUPPORT_EMAIL_DEFAULTS.items():
        if key not in sed.SYSTEM_EMAIL_DEFAULTS:
            sed.SYSTEM_EMAIL_DEFAULTS[key] = value


class SupportTicketEmailService:
    @staticmethod
    def customer_email(db: Session, ticket: SupportTicket) -> str | None:
        from app.services.support_ticket_service import ticket_requester_email

        return ticket_requester_email(db, ticket)

    @staticmethod
    def _variables(db: Session, ticket: SupportTicket, **extra: str) -> dict[str, str]:
        user = db.get(User, ticket.created_by_user_id)
        org = db.get(Organisation, ticket.organisation_id)
        from_name, from_email = SupportMailboxSettingsService.from_address(db)
        ref = ticket.public_ref or f"TKT-{ticket.id:06d}"
        requester = SupportTicketEmailService.customer_email(db, ticket) or ""
        name = (getattr(ticket, "requester_name", None) or "").strip()
        if not name:
            name = (getattr(user, "full_name", None) or getattr(user, "name", None) or "").strip()
        if not name and requester:
            name = requester.split("@")[0]
        if not name and user is not None:
            name = (getattr(user, "email", None) or "").split("@")[0]
        vars_: dict[str, str] = {
            "public_ref": ref,
            "subject": ticket.subject or "",
            "status": ticket.status or "",
            "customer_name": name or "there",
            "customer_email": requester or (getattr(user, "email", None) or ""),
            "organisation_name": (getattr(org, "name", None) or "your organisation"),
            "support_email": from_email or "support@voxbulk.com",
            "ticket_url": f"https://dashboard.voxbulk.com/account/support/tickets?ticket={ticket.id}",
            "admin_ticket_url": f"https://admin.voxbulk.com/support/tickets/{ticket.id}",
            "reply_body": "",
        }
        vars_.update({k: "" if v is None else str(v) for k, v in extra.items()})
        return vars_

    @staticmethod
    def _deliver(db: Session, *, to_addr: str, subject: str, body: str) -> tuple[bool, str | None]:
        from app.services.platform_sender_email_service import PlatformSenderEmailService

        outbound = PlatformSenderEmailService.resolve_outbound(db, "support")
        if outbound and outbound.get("from_email"):
            from_name = outbound.get("from_name") or "VOXBULK Support"
            from_email = outbound["from_email"]
            smtp_username = outbound.get("smtp_username")
            smtp_password = outbound.get("smtp_password")
        else:
            from_name, from_email = SupportMailboxSettingsService.from_address(db)
            row = SupportMailboxSettingsService.get_row(db)
            try:
                smtp_password = SupportMailboxSettingsService.get_decrypted_password(db)
            except Exception:
                smtp_password = None
            smtp_username = (getattr(row, "smtp_username", None) or from_email or "").strip() or None
        try:
            SmtpMailerService.send_html(
                db,
                to_addr=to_addr,
                subject=subject,
                body=body,
                from_email=from_email,
                from_name=from_name,
                smtp_username=smtp_username,
                smtp_password=smtp_password,
            )
            return True, None
        except SmtpMailerError as e:
            logger.warning("support_ticket_email_failed to=%s err=%s", to_addr, e)
            return False, str(e)
        except Exception as e:
            logger.exception("support_ticket_email_unexpected to=%s", to_addr)
            return False, str(e)[:300]

    @staticmethod
    def send_template(db: Session, *, template_key: str, to_email: str, ticket: SupportTicket, **extra: str) -> dict[str, Any]:
        register_support_email_defaults()
        em = (to_email or "").strip().lower()
        if not em or "@" not in em:
            return {"ok": False, "reason": "missing_recipient"}
        try:
            EmailTemplateService.ensure_system_templates(db)
            from app.services.transactional_email_service import TransactionalEmailService

            subject_tpl, body_tpl, enabled = TransactionalEmailService.load_template_fields(db, template_key=template_key)
            if not enabled:
                return {"ok": False, "reason": "template_disabled"}
            if not subject_tpl.strip() or not body_tpl.strip():
                defaults = SUPPORT_EMAIL_DEFAULTS.get(template_key) or {}
                subject_tpl = defaults.get("subject") or subject_tpl
                body_tpl = defaults.get("body") or body_tpl
            variables = SupportTicketEmailService._variables(db, ticket, **extra)
            subject = substitute_placeholders(subject_tpl, variables)
            body = substitute_placeholders(body_tpl, variables)
            ok, err = SupportTicketEmailService._deliver(db, to_addr=em, subject=subject, body=body)
            return {"ok": ok, "to": em, "error": err}
        except Exception as e:
            logger.exception("support_ticket_email_template_failed key=%s", template_key)
            return {"ok": False, "reason": "send_failed", "error": str(e)[:300]}

    @staticmethod
    def notify_created(db: Session, ticket: SupportTicket) -> dict[str, Any]:
        em = SupportTicketEmailService.customer_email(db, ticket)
        if not em:
            return {"ok": False, "reason": "missing_recipient"}
        return SupportTicketEmailService.send_template(db, template_key=SUPPORT_TICKET_CREATED, to_email=em, ticket=ticket)

    @staticmethod
    def notify_reply(db: Session, ticket: SupportTicket, *, reply_body: str) -> dict[str, Any]:
        em = SupportTicketEmailService.customer_email(db, ticket)
        if not em:
            return {"ok": False, "reason": "missing_recipient"}
        return SupportTicketEmailService.send_template(
            db, template_key=SUPPORT_TICKET_REPLY, to_email=em, ticket=ticket, reply_body=reply_body
        )

    @staticmethod
    def notify_status(db: Session, ticket: SupportTicket) -> dict[str, Any]:
        em = SupportTicketEmailService.customer_email(db, ticket)
        if not em:
            return {"ok": False, "reason": "missing_recipient"}
        return SupportTicketEmailService.send_template(db, template_key=SUPPORT_TICKET_STATUS, to_email=em, ticket=ticket)

    @staticmethod
    def notify_assigned(db: Session, ticket: SupportTicket) -> dict[str, Any]:
        if not ticket.assigned_admin_user_id:
            return {"ok": False, "reason": "unassigned"}
        au = db.get(AdminUser, ticket.assigned_admin_user_id)
        em = (getattr(au, "email", None) or "").strip().lower()
        if not em:
            return {"ok": False, "reason": "missing_admin_email"}
        return SupportTicketEmailService.send_template(db, template_key=SUPPORT_TICKET_ASSIGNED, to_email=em, ticket=ticket)
