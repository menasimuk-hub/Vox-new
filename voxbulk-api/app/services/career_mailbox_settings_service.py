from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.encryption import get_encryptor
from app.models.career_mailbox_settings import CAREER_MAILBOX_ROW_ID, CareerMailboxSettings


class CareerMailboxSettingsService:
    @staticmethod
    def get_row(db: Session) -> CareerMailboxSettings:
        obj = db.execute(select(CareerMailboxSettings).where(CareerMailboxSettings.id == CAREER_MAILBOX_ROW_ID)).scalar_one_or_none()
        if obj is None:
            obj = CareerMailboxSettings(id=CAREER_MAILBOX_ROW_ID)
            db.add(obj)
            db.commit()
            db.refresh(obj)
        return obj

    @staticmethod
    def compute_status(row: CareerMailboxSettings) -> tuple[bool, list[str]]:
        missing: list[str] = []
        if not (row.imap_host or "").strip():
            missing.append("imap_host")
        if not row.imap_port or row.imap_port <= 0:
            missing.append("imap_port")
        if not (row.mailbox_email or "").strip():
            missing.append("mailbox_email")
        if (row.imap_username or row.mailbox_email) and not (row.password_encrypted or "").strip():
            missing.append("password")
        return len(missing) == 0, missing

    @staticmethod
    def to_public_dict(db: Session, row: CareerMailboxSettings) -> dict[str, Any]:
        configured, missing = CareerMailboxSettingsService.compute_status(row)
        return {
            "mailbox_email": row.mailbox_email or "careers@voxbulk.com",
            "imap_host": row.imap_host or "",
            "imap_port": int(row.imap_port or 993),
            "imap_use_ssl": bool(row.imap_use_ssl),
            "imap_use_tls": bool(getattr(row, "imap_use_tls", False)),
            "imap_username": row.imap_username or "",
            "sync_interval_minutes": int(row.sync_interval_minutes or 15),
            "is_enabled": bool(row.is_enabled),
            "password_set": bool((row.password_encrypted or "").strip()),
            "configured": configured,
            "incomplete_fields": missing,
            "last_sync_at": row.last_sync_at.isoformat() if row.last_sync_at else None,
            "last_sync_ok": row.last_sync_ok,
            "last_sync_message": row.last_sync_message or "",
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def upsert(
        db: Session,
        *,
        mailbox_email: str,
        imap_host: str,
        imap_port: int,
        imap_use_ssl: bool,
        imap_use_tls: bool,
        imap_username: str | None,
        sync_interval_minutes: int,
        is_enabled: bool,
        password: str | None,
    ) -> CareerMailboxSettings:
        row = CareerMailboxSettingsService.get_row(db)
        row.mailbox_email = (mailbox_email or "careers@voxbulk.com").strip().lower()
        row.imap_host = (imap_host or "").strip()
        row.imap_port = int(imap_port or 993)
        row.imap_use_ssl = bool(imap_use_ssl)
        row.imap_use_tls = bool(imap_use_tls) and not bool(imap_use_ssl)
        row.imap_username = (imap_username or "").strip() or None
        row.sync_interval_minutes = max(5, min(int(sync_interval_minutes or 15), 240))
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
        row = CareerMailboxSettingsService.get_row(db)
        raw = row.password_encrypted
        if not raw:
            return None
        return get_encryptor().decrypt_str(raw)

    @staticmethod
    def record_sync_result(db: Session, *, ok: bool, message: str) -> None:
        row = CareerMailboxSettingsService.get_row(db)
        row.last_sync_at = datetime.utcnow()
        row.last_sync_ok = ok
        row.last_sync_message = (message or "")[:500]
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
