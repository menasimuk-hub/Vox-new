"""Support mailbox settings (SMTP out + IMAP receive → support tickets)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.encryption import get_encryptor
from app.models.support_mailbox_settings import SUPPORT_MAILBOX_ROW_ID, SupportMailboxSettings

DEFAULT_MAILBOX = "support@voxbulk.com"
DEFAULT_FROM_NAME = "VOXBULK Support"


class SupportMailboxSettingsService:
    @staticmethod
    def get_row(db: Session) -> SupportMailboxSettings:
        obj = db.execute(
            select(SupportMailboxSettings).where(SupportMailboxSettings.id == SUPPORT_MAILBOX_ROW_ID)
        ).scalar_one_or_none()
        if obj is None:
            obj = SupportMailboxSettings(id=SUPPORT_MAILBOX_ROW_ID)
            db.add(obj)
            db.commit()
            db.refresh(obj)
        return obj

    @staticmethod
    def compute_imap_status(row: SupportMailboxSettings) -> tuple[bool, list[str]]:
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
    def compute_smtp_status(row: SupportMailboxSettings) -> tuple[bool, list[str]]:
        missing: list[str] = []
        if not (row.mailbox_email or "").strip():
            missing.append("mailbox_email")
        dedicated = (row.smtp_host or "").strip()
        if dedicated:
            if not row.smtp_port or int(row.smtp_port) <= 0:
                missing.append("smtp_port")
            if not (row.password_encrypted or "").strip():
                missing.append("password")
        return len(missing) == 0, missing

    @staticmethod
    def to_public_dict(db: Session, row: SupportMailboxSettings) -> dict[str, Any]:
        imap_ok, imap_missing = SupportMailboxSettingsService.compute_imap_status(row)
        smtp_ok, smtp_missing = SupportMailboxSettingsService.compute_smtp_status(row)
        configured = imap_ok  # inbound→tickets is the primary contract
        return {
            "mailbox_email": row.mailbox_email or DEFAULT_MAILBOX,
            "from_name": row.from_name or DEFAULT_FROM_NAME,
            "smtp_username": row.smtp_username or "",
            "smtp_host": row.smtp_host or "",
            "smtp_port": int(row.smtp_port) if row.smtp_port else None,
            "imap_host": row.imap_host or "",
            "imap_port": int(row.imap_port or 993),
            "imap_use_ssl": bool(row.imap_use_ssl),
            "imap_use_tls": bool(getattr(row, "imap_use_tls", False)),
            "imap_username": row.imap_username or "",
            "sync_interval_minutes": int(row.sync_interval_minutes or 5),
            "is_enabled": bool(row.is_enabled),
            "password_set": bool((row.password_encrypted or "").strip()),
            "configured": configured,
            "smtp_ready": smtp_ok,
            "incomplete_fields": imap_missing,
            "smtp_incomplete_fields": smtp_missing,
            "last_sync_at": row.last_sync_at.isoformat() if row.last_sync_at else None,
            "last_sync_ok": row.last_sync_ok,
            "last_sync_message": row.last_sync_message or "",
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def from_address(db: Session) -> tuple[str, str]:
        row = SupportMailboxSettingsService.get_row(db)
        return (
            (row.from_name or DEFAULT_FROM_NAME).strip() or DEFAULT_FROM_NAME,
            (row.mailbox_email or DEFAULT_MAILBOX).strip().lower() or DEFAULT_MAILBOX,
        )

    @staticmethod
    def upsert(
        db: Session,
        *,
        mailbox_email: str,
        from_name: str,
        smtp_username: str | None,
        smtp_host: str | None,
        smtp_port: int | None,
        imap_host: str,
        imap_port: int,
        imap_use_ssl: bool,
        imap_use_tls: bool,
        imap_username: str | None,
        sync_interval_minutes: int,
        is_enabled: bool,
        password: str | None,
    ) -> SupportMailboxSettings:
        row = SupportMailboxSettingsService.get_row(db)
        row.mailbox_email = (mailbox_email or DEFAULT_MAILBOX).strip().lower()
        row.from_name = (from_name or DEFAULT_FROM_NAME).strip() or DEFAULT_FROM_NAME
        row.smtp_username = (smtp_username or "").strip() or None
        row.smtp_host = (smtp_host or "").strip() or None
        if smtp_port is not None:
            try:
                port_val = int(smtp_port)
                row.smtp_port = port_val if port_val > 0 else None
            except (TypeError, ValueError):
                row.smtp_port = None
        else:
            row.smtp_port = None
        row.imap_host = (imap_host or "").strip() or None
        row.imap_port = int(imap_port or 993)
        row.imap_use_ssl = bool(imap_use_ssl)
        row.imap_use_tls = bool(imap_use_tls) and not bool(imap_use_ssl)
        row.imap_username = (imap_username or "").strip() or None
        row.sync_interval_minutes = max(1, min(int(sync_interval_minutes or 5), 240))
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
        row = SupportMailboxSettingsService.get_row(db)
        raw = row.password_encrypted
        if not raw:
            return None
        return get_encryptor().decrypt_str(raw)

    @staticmethod
    def record_sync_result(db: Session, *, ok: bool, message: str) -> None:
        row = SupportMailboxSettingsService.get_row(db)
        row.last_sync_at = datetime.utcnow()
        row.last_sync_ok = ok
        row.last_sync_message = (message or "")[:500]
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
