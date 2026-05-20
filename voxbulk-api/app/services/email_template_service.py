from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.email_template import EmailTemplate

EMAIL_TEMPLATE_KEYS: tuple[str, ...] = (
    "new_user",
    "forgot_password",
    "new_invoice",
    "payment_failed",
    "general_notification",
)

_TEMPLATE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


class EmailTemplateUnknown(ValueError):
    pass


class EmailTemplateError(ValueError):
    pass


class EmailTemplateService:
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
    def list_all(db: Session) -> list[dict[str, Any]]:
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
