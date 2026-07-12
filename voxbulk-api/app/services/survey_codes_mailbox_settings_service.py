"""Survey codes mailbox (outbound From for AI follow-up promo emails)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.encryption import get_encryptor
from app.models.survey_codes_mailbox_settings import (
    SURVEY_CODES_MAILBOX_ROW_ID,
    SurveyCodesMailboxSettings,
)

DEFAULT_MAILBOX = "survey.codes@voxbulk.com"
DEFAULT_FROM_NAME = "VOXBULK Survey Codes"


class SurveyCodesMailboxSettingsService:
    @staticmethod
    def get_row(db: Session) -> SurveyCodesMailboxSettings:
        obj = db.execute(
            select(SurveyCodesMailboxSettings).where(SurveyCodesMailboxSettings.id == SURVEY_CODES_MAILBOX_ROW_ID)
        ).scalar_one_or_none()
        if obj is None:
            obj = SurveyCodesMailboxSettings(
                id=SURVEY_CODES_MAILBOX_ROW_ID,
                mailbox_email=DEFAULT_MAILBOX,
                from_name=DEFAULT_FROM_NAME,
            )
            db.add(obj)
            db.commit()
            db.refresh(obj)
        return obj

    @staticmethod
    def compute_status(row: SurveyCodesMailboxSettings) -> tuple[bool, list[str]]:
        missing: list[str] = []
        if not (row.mailbox_email or "").strip():
            missing.append("mailbox_email")
        return len(missing) == 0, missing

    @staticmethod
    def to_public_dict(db: Session, row: SurveyCodesMailboxSettings) -> dict[str, Any]:
        configured, missing = SurveyCodesMailboxSettingsService.compute_status(row)
        return {
            "mailbox_email": row.mailbox_email or DEFAULT_MAILBOX,
            "from_name": row.from_name or DEFAULT_FROM_NAME,
            "smtp_username": row.smtp_username or "",
            "is_enabled": bool(row.is_enabled),
            "password_set": bool((row.password_encrypted or "").strip()),
            "configured": configured,
            "incomplete_fields": missing,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def upsert(
        db: Session,
        *,
        mailbox_email: str,
        from_name: str,
        smtp_username: str | None,
        is_enabled: bool,
        password: str | None,
    ) -> SurveyCodesMailboxSettings:
        row = SurveyCodesMailboxSettingsService.get_row(db)
        row.mailbox_email = (mailbox_email or DEFAULT_MAILBOX).strip().lower()
        row.from_name = (from_name or DEFAULT_FROM_NAME).strip() or DEFAULT_FROM_NAME
        row.smtp_username = (smtp_username or "").strip() or None
        row.is_enabled = bool(is_enabled)
        row.updated_at = datetime.utcnow()
        if password is not None and str(password).strip():
            row.password_encrypted = get_encryptor().encrypt_str(str(password).strip())
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def get_decrypted_password(db: Session) -> str | None:
        row = SurveyCodesMailboxSettingsService.get_row(db)
        raw = row.password_encrypted
        if not raw:
            return None
        return get_encryptor().decrypt_str(raw)

    @staticmethod
    def from_address(db: Session) -> tuple[str, str]:
        row = SurveyCodesMailboxSettingsService.get_row(db)
        email = str(row.mailbox_email or DEFAULT_MAILBOX).strip().lower()
        name = str(row.from_name or DEFAULT_FROM_NAME).strip() or DEFAULT_FROM_NAME
        return name, email
