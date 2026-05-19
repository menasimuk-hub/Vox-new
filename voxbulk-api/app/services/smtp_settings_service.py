from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.encryption import get_encryptor
from app.models.smtp_settings import SmtpSettings

SMTP_ROW_ID = 1


class SmtpSettingsService:
    @staticmethod
    def get_row(db: Session) -> SmtpSettings:
        obj = db.execute(select(SmtpSettings).where(SmtpSettings.id == SMTP_ROW_ID)).scalar_one_or_none()
        if obj is None:
            obj = SmtpSettings(id=SMTP_ROW_ID)
            db.add(obj)
            db.commit()
            db.refresh(obj)
        return obj

    @staticmethod
    def _needs_password(row: SmtpSettings) -> bool:
        u = (row.username or "").strip()
        return bool(u)

    @staticmethod
    def compute_status(row: SmtpSettings) -> tuple[bool, list[str]]:
        missing: list[str] = []
        if not (row.host or "").strip():
            missing.append("host")
        if not row.port or row.port <= 0:
            missing.append("port")
        if not (row.from_email or "").strip():
            missing.append("from_email")
        if not (row.from_name or "").strip():
            missing.append("from_name")
        if SmtpSettingsService._needs_password(row) and not (row.password_encrypted or "").strip():
            missing.append("password")

        configured = len(missing) == 0
        return configured, missing

    @staticmethod
    def to_public_dict(db: Session, row: SmtpSettings) -> dict[str, Any]:
        configured, missing = SmtpSettingsService.compute_status(row)
        pwd_set = bool((row.password_encrypted or "").strip())
        return {
            "host": row.host or "",
            "port": int(row.port or 587),
            "username": row.username or "",
            "from_name": row.from_name or "",
            "from_email": row.from_email or "",
            "use_tls": bool(row.use_tls),
            "use_ssl": bool(row.use_ssl),
            "is_enabled": bool(row.is_enabled),
            "password_set": pwd_set,
            "configured": configured,
            "incomplete_fields": missing,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def upsert(
        db: Session,
        *,
        host: str,
        port: int,
        username: str | None,
        from_name: str,
        from_email: str,
        use_tls: bool,
        use_ssl: bool,
        is_enabled: bool,
        password: str | None,
    ) -> SmtpSettings:
        row = SmtpSettingsService.get_row(db)
        row.host = (host or "").strip()
        row.port = int(port or 587)
        row.username = (username or "").strip()
        row.from_name = (from_name or "").strip()
        row.from_email = (from_email or "").strip().lower()
        row.use_tls = bool(use_tls)
        row.use_ssl = bool(use_ssl)
        row.is_enabled = bool(is_enabled)
        row.updated_at = datetime.utcnow()

        if password is not None and str(password).strip():
            enc = get_encryptor()
            row.password_encrypted = enc.encrypt_str(str(password).strip())

        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def get_decrypted_password(db: Session) -> str | None:
        row = SmtpSettingsService.get_row(db)
        raw = row.password_encrypted
        if not raw:
            return None
        enc = get_encryptor()
        return enc.decrypt_str(raw)
