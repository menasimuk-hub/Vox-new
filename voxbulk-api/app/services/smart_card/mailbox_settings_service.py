"""Smart Card QR mailbox settings (outbound From + IMAP inbox)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.encryption import get_encryptor
from app.models.smart_card_mailbox_settings import SMART_CARD_MAILBOX_ROW_ID, SmartCardMailboxSettings

DEFAULT_MAILBOX = "smartqr@voxbulk.com"
DEFAULT_FROM_NAME = "VOXBULK Smart Card QR"


class SmartCardMailboxSettingsService:
    @staticmethod
    def get_row(db: Session) -> SmartCardMailboxSettings:
        obj = db.execute(
            select(SmartCardMailboxSettings).where(SmartCardMailboxSettings.id == SMART_CARD_MAILBOX_ROW_ID)
        ).scalar_one_or_none()
        if obj is None:
            obj = SmartCardMailboxSettings(
                id=SMART_CARD_MAILBOX_ROW_ID,
                mailbox_email=DEFAULT_MAILBOX,
                from_name=DEFAULT_FROM_NAME,
                is_enabled=True,
                imap_port=993,
                imap_use_ssl=True,
                imap_use_tls=False,
            )
            db.add(obj)
            db.commit()
            db.refresh(obj)
        return obj

    @staticmethod
    def from_address(db: Session) -> tuple[str, str]:
        row = SmartCardMailboxSettingsService.get_row(db)
        email = str(row.mailbox_email or DEFAULT_MAILBOX).strip().lower() or DEFAULT_MAILBOX
        name = str(row.from_name or DEFAULT_FROM_NAME).strip() or DEFAULT_FROM_NAME
        return name, email

    @staticmethod
    def compute_imap_status(row: SmartCardMailboxSettings) -> tuple[bool, list[str]]:
        missing: list[str] = []
        if not (row.imap_host or "").strip():
            missing.append("imap_host")
        if not row.imap_port or int(row.imap_port) <= 0:
            missing.append("imap_port")
        if not (row.mailbox_email or "").strip():
            missing.append("mailbox_email")
        has_user = bool((row.imap_username or row.mailbox_email or "").strip())
        has_pwd = bool((row.imap_password_encrypted or "").strip())
        if has_user and not has_pwd:
            missing.append("imap_password")
        return len(missing) == 0, missing

    @staticmethod
    def to_public_dict(db: Session) -> dict[str, Any]:
        row = SmartCardMailboxSettingsService.get_row(db)
        imap_ok, imap_missing = SmartCardMailboxSettingsService.compute_imap_status(row)
        return {
            "mailbox_email": row.mailbox_email or DEFAULT_MAILBOX,
            "from_name": row.from_name or DEFAULT_FROM_NAME,
            "smtp_username": row.smtp_username or "",
            "smtp_host": row.smtp_host or "",
            "smtp_port": int(row.smtp_port) if row.smtp_port else None,
            "is_enabled": bool(row.is_enabled),
            "password_set": bool((row.password_encrypted or "").strip()),
            "imap_host": row.imap_host or "",
            "imap_port": int(row.imap_port or 993),
            "imap_use_ssl": bool(row.imap_use_ssl),
            "imap_use_tls": bool(row.imap_use_tls),
            "imap_username": row.imap_username or "",
            "imap_password_set": bool((row.imap_password_encrypted or "").strip()),
            "imap_configured": imap_ok,
            "imap_incomplete_fields": imap_missing,
            "imap_last_sync_at": row.imap_last_sync_at.isoformat() if row.imap_last_sync_at else None,
            "imap_last_sync_message": row.imap_last_sync_message or "",
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def upsert(
        db: Session,
        *,
        mailbox_email: str,
        from_name: str,
        smtp_username: str | None = None,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        is_enabled: bool = True,
        password: str | None = None,
        imap_host: str | None = None,
        imap_port: int | None = None,
        imap_use_ssl: bool | None = None,
        imap_use_tls: bool | None = None,
        imap_username: str | None = None,
        imap_password: str | None = None,
    ) -> SmartCardMailboxSettings:
        row = SmartCardMailboxSettingsService.get_row(db)
        row.mailbox_email = (mailbox_email or DEFAULT_MAILBOX).strip().lower()
        row.from_name = (from_name or DEFAULT_FROM_NAME).strip() or DEFAULT_FROM_NAME
        row.smtp_username = (smtp_username or "").strip() or None
        if smtp_host is not None:
            row.smtp_host = (smtp_host or "").strip() or None
        if smtp_port is not None:
            try:
                port_val = int(smtp_port)
                row.smtp_port = port_val if port_val > 0 else None
            except (TypeError, ValueError):
                pass
        row.is_enabled = bool(is_enabled)
        if imap_host is not None:
            row.imap_host = (imap_host or "").strip() or None
        if imap_port is not None:
            try:
                row.imap_port = int(imap_port) or 993
            except (TypeError, ValueError):
                row.imap_port = 993
        if imap_use_ssl is not None:
            row.imap_use_ssl = bool(imap_use_ssl)
        if imap_use_tls is not None:
            row.imap_use_tls = bool(imap_use_tls) and not bool(row.imap_use_ssl)
        if imap_username is not None:
            row.imap_username = (imap_username or "").strip() or None
        row.updated_at = datetime.utcnow()
        if password is not None and str(password).strip():
            row.password_encrypted = get_encryptor().encrypt_str(str(password).strip())
        if imap_password is not None and str(imap_password).strip():
            row.imap_password_encrypted = get_encryptor().encrypt_str(str(imap_password).strip())
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def get_decrypted_password(db: Session) -> str | None:
        row = SmartCardMailboxSettingsService.get_row(db)
        raw = row.password_encrypted
        if not raw:
            return None
        return get_encryptor().decrypt_str(raw)

    @staticmethod
    def get_decrypted_imap_password(db: Session) -> str | None:
        row = SmartCardMailboxSettingsService.get_row(db)
        raw = row.imap_password_encrypted
        if not raw:
            return None
        return get_encryptor().decrypt_str(raw)

    @staticmethod
    def record_imap_sync(db: Session, *, message: str) -> None:
        row = SmartCardMailboxSettingsService.get_row(db)
        row.imap_last_sync_at = datetime.utcnow()
        row.imap_last_sync_message = (message or "")[:500]
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
