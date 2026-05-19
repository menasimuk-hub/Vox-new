from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.email_template_service import EMAIL_TEMPLATE_KEYS, EmailTemplateService
from app.services.smtp_mailer_service import SmtpMailerError, SmtpMailerService

logger = logging.getLogger(__name__)

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def substitute_placeholders(template: str, variables: dict[str, str]) -> str:
    if not template:
        return ""

    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        return variables.get(key, m.group(0))

    return _PLACEHOLDER.sub(repl, template)


class TransactionalEmailService:
    """Sends SMTP mail using persisted templates + simple {{placeholder}} substitution."""

    @staticmethod
    def send_templated_optional(
        db: Session,
        *,
        template_key: str,
        to_email: str,
        variables: dict[str, str],
    ) -> tuple[bool, str | None]:
        """
        Sends if template exists, is enabled, and SMTP works.
        Never raises SMTP errors to callers (product flows stay stable).

        Returns: (attempted_mail_send, error_message_or_none)
        """
        k = (template_key or "").strip().lower()
        if k not in EMAIL_TEMPLATE_KEYS:
            return False, "unknown_template"

        row = EmailTemplateService.get(db, key=k)
        if row is None or not row.is_enabled:
            logger.info("transactional_skip_disabled", extra={"template": k})
            return False, None

        to_addr = (to_email or "").strip().lower()
        if not to_addr:
            return False, "missing_recipient"

        subject = substitute_placeholders(row.subject or "", variables)
        body = substitute_placeholders(row.body or "", variables)
        try:
            SmtpMailerService.send_html(db, to_addr=to_addr, subject=subject, body=body)
        except SmtpMailerError as e:
            logger.warning("transactional_smtp_failed", extra={"template": k, "err": str(e)})
            return False, str(e)
        return True, None
