from __future__ import annotations

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


class EmailTemplateUnknown(ValueError):
    pass


class EmailTemplateService:
    @staticmethod
    def assert_key(key: str) -> str:
        k = (key or "").strip().lower()
        if k not in EMAIL_TEMPLATE_KEYS:
            raise EmailTemplateUnknown(f"Unknown template key: {key}")
        return k

    @staticmethod
    def list_all(db: Session) -> list[dict[str, Any]]:
        rows = db.execute(select(EmailTemplate).order_by(EmailTemplate.template_key.asc())).scalars().all()
        return [EmailTemplateService.to_dict(r) for r in rows]

    @staticmethod
    def get(db: Session, *, key: str) -> EmailTemplate | None:
        k = EmailTemplateService.assert_key(key)
        return db.execute(select(EmailTemplate).where(EmailTemplate.template_key == k)).scalar_one_or_none()

    @staticmethod
    def to_dict(row: EmailTemplate) -> dict[str, Any]:
        return {
            "template_key": row.template_key,
            "subject": row.subject or "",
            "body": row.body or "",
            "is_enabled": bool(row.is_enabled),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def upsert(
        db: Session,
        *,
        key: str,
        subject: str,
        body: str,
        is_enabled: bool,
    ) -> EmailTemplate:
        k = EmailTemplateService.assert_key(key)
        row = EmailTemplateService.get(db, key=k)
        if row is None:
            row = EmailTemplate(template_key=k)
            db.add(row)
            db.flush()
        row.subject = (subject or "").strip()
        row.body = body or ""
        row.is_enabled = bool(is_enabled)
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
