from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.transactional_email_service import TransactionalEmailService

logger = logging.getLogger(__name__)


class ProductEmailTriggers:
    """Reusable hooks product code can call; invoice/payments call when wired."""

    @staticmethod
    def welcome_variables(*, to_email: str, organisation_name: str = "") -> dict[str, str]:
        settings = get_settings()
        em = (to_email or "").strip().lower()
        local = em.split("@")[0] if em and "@" in em else "there"
        dashboard_url = str(settings.dashboard_app_origin or "https://dashboard.voxbulk.com").rstrip("/")
        signin_url = f"{str(settings.public_app_origin or 'https://voxbulk.com').rstrip('/')}/signin"
        return {
            "user_email": em,
            "user_name": local,
            "first_name": local,
            "organisation_name": organisation_name or "",
            "dashboard_url": dashboard_url,
            "signin_url": signin_url,
        }

    @staticmethod
    def send_new_user_welcome(
        db: Session, *, to_email: str, extra_variables: dict[str, str] | None = None
    ) -> tuple[bool, str | None]:
        em = (to_email or "").strip().lower()
        if not em:
            return False, "missing_recipient"
        vars_: dict[str, str] = ProductEmailTriggers.welcome_variables(to_email=em)
        if extra_variables:
            for k, v in extra_variables.items():
                vars_[str(k)] = str(v)
        return TransactionalEmailService.send_templated_optional(
            db, template_key="new_user", to_email=em, variables=vars_
        )

    @staticmethod
    def send_new_user_welcome_safe(
        db: Session, *, to_email: str, organisation_name: str = ""
    ) -> tuple[bool, str | None]:
        """Send welcome mail without raising; logs skip/failure for ops visibility."""
        try:
            ok, err = ProductEmailTriggers.send_new_user_welcome(
                db,
                to_email=to_email,
                extra_variables={"organisation_name": organisation_name or ""},
            )
            if not ok and err:
                logger.warning(
                    "welcome_email_skipped",
                    extra={"to_email": to_email, "reason": err},
                )
            return ok, err
        except Exception as exc:
            logger.warning(
                "welcome_email_failed",
                extra={"to_email": to_email, "error": str(exc)},
            )
            return False, str(exc)

    @staticmethod
    def send_account_deletion_completed(
        db: Session,
        *,
        to_email: str,
        organisation_name: str,
        deleted_at: datetime,
    ) -> tuple[bool, str | None]:
        em = (to_email or "").strip().lower()
        if not em:
            return False, "missing_recipient"
        local = em.split("@")[0] if "@" in em else "there"
        vars_: dict[str, str] = {
            "user_email": em,
            "first_name": local,
            "user_name": local,
            "organisation_name": organisation_name or "",
            "deleted_at": deleted_at.strftime("%d %B %Y %H:%M UTC"),
            "retention_note": (
                "Invoices and legally required billing records are retained without personal identifiers. "
                "Support history may be kept for compliance."
            ),
            "support_email": "support@voxbulk.com",
        }
        return TransactionalEmailService.send_templated_optional(
            db,
            template_key="account_deletion_completed",
            to_email=em,
            variables=vars_,
        )

    @staticmethod
    def notify_payment_failed(
        db: Session,
        *,
        to_email: str,
        extra_variables: dict[str, Any] | None = None,
    ) -> tuple[bool, str | None]:
        em = (to_email or "").strip().lower()
        if not em:
            return False, "missing_recipient"
        vars_: dict[str, str] = {"user_email": em}
        if extra_variables:
            for k, v in (extra_variables or {}).items():
                vars_[str(k)] = "" if v is None else str(v)
        return TransactionalEmailService.send_templated_optional(
            db, template_key="payment_failed", to_email=em, variables=vars_
        )

    @staticmethod
    def notify_new_invoice(
        db: Session,
        *,
        to_email: str,
        extra_variables: dict[str, Any] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> tuple[bool, str | None]:
        em = (to_email or "").strip().lower()
        if not em:
            return False, "missing_recipient"
        vars_: dict[str, str] = {"user_email": em}
        if extra_variables:
            for k, v in (extra_variables or {}).items():
                vars_[str(k)] = "" if v is None else str(v)
        return TransactionalEmailService.send_templated_optional(
            db, template_key="new_invoice", to_email=em, variables=vars_, attachments=attachments
        )

    @staticmethod
    def notify_payment_receipt(
        db: Session,
        *,
        to_email: str,
        extra_variables: dict[str, Any] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> tuple[bool, str | None]:
        em = (to_email or "").strip().lower()
        if not em:
            return False, "missing_recipient"
        vars_: dict[str, str] = {"user_email": em}
        if extra_variables:
            for k, v in (extra_variables or {}).items():
                vars_[str(k)] = "" if v is None else str(v)
        return TransactionalEmailService.send_templated_optional(
            db,
            template_key="payment_receipt",
            to_email=em,
            variables=vars_,
            attachments=attachments,
        )

    @staticmethod
    def notify_general(
        db: Session,
        *,
        to_email: str,
        extra_variables: dict[str, Any] | None = None,
    ) -> tuple[bool, str | None]:
        em = (to_email or "").strip().lower()
        if not em:
            return False, "missing_recipient"
        vars_: dict[str, str] = {"user_email": em}
        if extra_variables:
            for k, v in (extra_variables or {}).items():
                vars_[str(k)] = "" if v is None else str(v)
        return TransactionalEmailService.send_templated_optional(
            db, template_key="general_notification", to_email=em, variables=vars_
        )
