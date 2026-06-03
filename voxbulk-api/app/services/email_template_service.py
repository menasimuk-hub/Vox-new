from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.email_template import EmailTemplate
from app.data.system_email_defaults import SYSTEM_EMAIL_DEFAULTS

EMAIL_TEMPLATE_KEYS: tuple[str, ...] = (
    "new_user",
    "forgot_password",
    "new_invoice",
    "invoice_document",
    "payment_failed",
    "general_notification",
    "sales_offer",
    "usage_warning",
    "interview_scheduling_invite",
    "interview_booking_invite",
    "interview_booking_confirm",
    "interview_booking_reminder",
    "interview_booking_cancel",
    "interview_campaign_cancelled",
    "interview_zoom_invite",
    "interview_missed_call_followup",
)

_TEMPLATE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


class EmailTemplateUnknown(ValueError):
    pass


class EmailTemplateError(ValueError):
    pass


class EmailTemplateService:
    @staticmethod
    def ensure_system_templates(db: Session) -> None:
        """Insert any missing system templates; refresh interview bodies with broken data: logos."""
        changed = False
        for key in EMAIL_TEMPLATE_KEYS:
            defaults = SYSTEM_EMAIL_DEFAULTS.get(key, {})
            row = EmailTemplateService.get(db, key=key)
            if row is None:
                EmailTemplateService.create(
                    db,
                    key=key,
                    title=defaults.get("title") or key.replace("_", " ").title(),
                    subject=defaults.get("subject") or key.replace("_", " ").title(),
                    body=defaults.get("body") or "",
                    is_enabled=True,
                )
                continue
            body = str(row.body or "")
            default_body = str(defaults.get("body") or "")
            default_subject = str(defaults.get("subject") or "")
            needs_calendar_refresh = (
                key in {"interview_booking_confirm", "interview_booking_reminder"}
                and default_body
                and "{{calendar_links_html}}" in default_body
                and "{{calendar_links_html}}" not in body
            )
            needs_cancel_refresh = (
                key in {"interview_booking_cancel", "interview_campaign_cancelled"}
                and default_body
                and (not body.strip() or not bool(row.is_enabled))
            )
            if default_body and key.startswith("interview_") and (
                "data:image" in body
                or ("data:" in body and "base64" in body)
                or needs_calendar_refresh
                or needs_cancel_refresh
            ):
                row.body = default_body
                if default_subject:
                    row.subject = default_subject
                row.updated_at = datetime.utcnow()
                db.add(row)
                changed = True
        if changed:
            db.commit()

    @staticmethod
    def is_system_key(key: str) -> bool:
        return (key or "").strip().lower() in EMAIL_TEMPLATE_KEYS

    @staticmethod
    def normalize_key(key: str) -> str:
        k = (key or "").strip().lower().replace("-", "_").replace(" ", "_")
        if not _TEMPLATE_KEY_RE.match(k):
            raise EmailTemplateError(
                "Template key must be 3–64 chars: lowercase letters, numbers, underscores; start with a letter."
            )
        return k

    @staticmethod
    def assert_key(key: str) -> str:
        k = EmailTemplateService.normalize_key(key)
        return k

    @staticmethod
    def get_send_content(db: Session, *, key: str) -> tuple[str, str, bool]:
        """
        Load subject/body for outbound mail or PDF rendering.
        When a DB row exists, use saved admin content only (no silent merge with code defaults).
        """
        k = EmailTemplateService.normalize_key(key)
        EmailTemplateService.ensure_system_templates(db)
        row = EmailTemplateService.get(db, key=k)
        defaults = SYSTEM_EMAIL_DEFAULTS.get(k, {})
        if row is not None:
            db.refresh(row)
            subject = str(row.subject or "")
            body = str(row.body or "")
            enabled = bool(row.is_enabled)
            if k.startswith("interview_"):
                subj = str(subject or defaults.get("subject") or "").strip()
                bod = str(body or defaults.get("body") or "").strip()
                if subj or bod:
                    # Interview outreach must send when content exists — do not block on is_enabled=false.
                    return subj, bod, True
                return (
                    str(defaults.get("subject") or ""),
                    str(defaults.get("body") or ""),
                    True,
                )
            return subject, body, enabled
        return str(defaults.get("subject") or ""), str(defaults.get("body") or ""), True

    @staticmethod
    def list_all(db: Session) -> list[dict[str, Any]]:
        EmailTemplateService.ensure_system_templates(db)
        rows = db.execute(select(EmailTemplate).order_by(EmailTemplate.template_key.asc())).scalars().all()
        return [EmailTemplateService.to_dict(r) for r in rows]

    @staticmethod
    def get(db: Session, *, key: str) -> EmailTemplate | None:
        k = EmailTemplateService.normalize_key(key)
        return db.execute(select(EmailTemplate).where(EmailTemplate.template_key == k)).scalar_one_or_none()

    @staticmethod
    def to_dict(row: EmailTemplate) -> dict[str, Any]:
        return {
            "id": row.id,
            "template_key": row.template_key,
            "title": row.title or "",
            "subject": row.subject or "",
            "body": row.body or "",
            "is_enabled": bool(row.is_enabled),
            "is_system": EmailTemplateService.is_system_key(row.template_key),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def create(
        db: Session,
        *,
        key: str,
        title: str,
        subject: str,
        body: str,
        is_enabled: bool,
    ) -> EmailTemplate:
        k = EmailTemplateService.normalize_key(key)
        if EmailTemplateService.get(db, key=k) is not None:
            raise EmailTemplateError(f"Template key already exists: {k}")
        now = datetime.utcnow()
        row = EmailTemplate(
            template_key=k,
            title=(title or k).strip(),
            subject=(subject or "").strip(),
            body=body or "",
            is_enabled=bool(is_enabled),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def upsert(
        db: Session,
        *,
        key: str,
        title: str | None = None,
        subject: str,
        body: str,
        is_enabled: bool,
    ) -> EmailTemplate:
        k = EmailTemplateService.normalize_key(key)
        row = EmailTemplateService.get(db, key=k)
        if row is None:
            return EmailTemplateService.create(
                db,
                key=k,
                title=title or k,
                subject=subject,
                body=body,
                is_enabled=is_enabled,
            )
        if title is not None:
            row.title = title.strip()
        row.subject = (subject or "").strip()
        row.body = body or ""
        row.is_enabled = bool(is_enabled)
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def delete(db: Session, *, key: str) -> None:
        k = EmailTemplateService.normalize_key(key)
        if EmailTemplateService.is_system_key(k):
            raise EmailTemplateError("System templates cannot be deleted")
        row = EmailTemplateService.get(db, key=k)
        if row is None:
            raise EmailTemplateUnknown(f"Unknown template key: {k}")
        db.delete(row)
        db.commit()
