from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.transactional_email_service import TransactionalEmailService


class ProductEmailTriggers:
    """Reusable hooks product code can call; invoice/payments call when wired."""

    @staticmethod
    def send_new_user_welcome(
        db: Session, *, to_email: str, extra_variables: dict[str, str] | None = None
    ) -> tuple[bool, str | None]:
        em = (to_email or "").strip().lower()
        if not em:
            return False, "missing_recipient"
        vars_: dict[str, str] = {"user_email": em}
        if extra_variables:
            for k, v in extra_variables.items():
                vars_[str(k)] = str(v)
        return TransactionalEmailService.send_templated_optional(
            db, template_key="new_user", to_email=em, variables=vars_
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
