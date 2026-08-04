"""CRUD for platform sender emails (@voxbulk.com) used as SMTP From overrides."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.platform_sender_email import SENDER_DOMAIN, PlatformSenderEmail

_LOCAL_RE = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,62}$", re.I)
_PURPOSE_RE = re.compile(r"^[a-z0-9_]{1,40}$", re.I)


class PlatformSenderEmailError(Exception):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class PlatformSenderEmailService:
    @staticmethod
    def normalize_local_part(raw: str) -> str:
        text = str(raw or "").strip().lower()
        if "@" in text:
            local, _, domain = text.partition("@")
            if domain and domain != SENDER_DOMAIN:
                raise PlatformSenderEmailError(f"Domain must be @{SENDER_DOMAIN}")
            text = local
        if not _LOCAL_RE.match(text):
            raise PlatformSenderEmailError("Invalid local-part (use letters, numbers, . _ + -)")
        return text

    @staticmethod
    def normalize_purpose(raw: str) -> str:
        text = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
        if not text:
            return ""
        if not _PURPOSE_RE.match(text):
            raise PlatformSenderEmailError("Purpose must be alphanumeric / underscore (max 40)")
        return text

    @staticmethod
    def to_dict(row: PlatformSenderEmail) -> dict[str, Any]:
        return {
            "id": row.id,
            "local_part": row.local_part,
            "email": row.email,
            "from_name": row.from_name or "",
            "purpose": row.purpose or "",
            "is_active": bool(row.is_active),
            "notes": row.notes,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def list_all(db: Session) -> list[PlatformSenderEmail]:
        return list(
            db.execute(
                select(PlatformSenderEmail).order_by(
                    PlatformSenderEmail.purpose.asc(),
                    PlatformSenderEmail.local_part.asc(),
                )
            ).scalars().all()
        )

    @staticmethod
    def get(db: Session, row_id: str) -> PlatformSenderEmail | None:
        return db.execute(
            select(PlatformSenderEmail).where(PlatformSenderEmail.id == row_id)
        ).scalar_one_or_none()

    @staticmethod
    def get_sender_by_purpose(db: Session, purpose: str) -> tuple[str, str] | None:
        """Return (from_name, email) for an active row with this purpose, else None."""
        key = PlatformSenderEmailService.normalize_purpose(purpose)
        if not key:
            return None
        row = db.execute(
            select(PlatformSenderEmail).where(
                PlatformSenderEmail.purpose == key,
                PlatformSenderEmail.is_active.is_(True),
            )
        ).scalars().first()
        if row is None:
            return None
        return (row.from_name or row.local_part, row.email)

    @staticmethod
    def create(
        db: Session,
        *,
        local_part: str,
        from_name: str = "",
        purpose: str = "",
        notes: str | None = None,
        is_active: bool = True,
    ) -> PlatformSenderEmail:
        local = PlatformSenderEmailService.normalize_local_part(local_part)
        purpose_n = PlatformSenderEmailService.normalize_purpose(purpose)
        exists = db.execute(
            select(PlatformSenderEmail).where(PlatformSenderEmail.local_part == local)
        ).scalar_one_or_none()
        if exists is not None:
            raise PlatformSenderEmailError(f"{local}@{SENDER_DOMAIN} already exists")
        if purpose_n:
            clash = db.execute(
                select(PlatformSenderEmail).where(
                    PlatformSenderEmail.purpose == purpose_n,
                    PlatformSenderEmail.is_active.is_(True),
                )
            ).scalar_one_or_none()
            if clash is not None:
                raise PlatformSenderEmailError(f"Purpose '{purpose_n}' already used by {clash.email}")
        now = datetime.utcnow()
        row = PlatformSenderEmail(
            id=str(uuid.uuid4()),
            local_part=local,
            from_name=(from_name or "").strip() or local.title(),
            purpose=purpose_n,
            is_active=bool(is_active),
            notes=(notes or "").strip() or None,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def update(db: Session, row_id: str, patch: dict[str, Any]) -> PlatformSenderEmail:
        row = PlatformSenderEmailService.get(db, row_id)
        if row is None:
            raise PlatformSenderEmailError("Sender not found", status_code=404)
        if "local_part" in patch and patch["local_part"] is not None:
            local = PlatformSenderEmailService.normalize_local_part(str(patch["local_part"]))
            if local != row.local_part:
                exists = db.execute(
                    select(PlatformSenderEmail).where(PlatformSenderEmail.local_part == local)
                ).scalar_one_or_none()
                if exists is not None:
                    raise PlatformSenderEmailError(f"{local}@{SENDER_DOMAIN} already exists")
                row.local_part = local
        if "from_name" in patch and patch["from_name"] is not None:
            row.from_name = str(patch["from_name"]).strip()
        if "purpose" in patch and patch["purpose"] is not None:
            purpose_n = PlatformSenderEmailService.normalize_purpose(str(patch["purpose"]))
            if purpose_n and purpose_n != row.purpose:
                clash = db.execute(
                    select(PlatformSenderEmail).where(
                        PlatformSenderEmail.purpose == purpose_n,
                        PlatformSenderEmail.is_active.is_(True),
                        PlatformSenderEmail.id != row.id,
                    )
                ).scalar_one_or_none()
                if clash is not None:
                    raise PlatformSenderEmailError(f"Purpose '{purpose_n}' already used by {clash.email}")
            row.purpose = purpose_n
        if "notes" in patch:
            row.notes = (str(patch["notes"]).strip() if patch["notes"] is not None else None) or None
        if "is_active" in patch and patch["is_active"] is not None:
            row.is_active = bool(patch["is_active"])
        row.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def freeze(db: Session, row_id: str, *, frozen: bool = True) -> PlatformSenderEmail:
        return PlatformSenderEmailService.update(db, row_id, {"is_active": not frozen})

    @staticmethod
    def delete(db: Session, row_id: str) -> None:
        row = PlatformSenderEmailService.get(db, row_id)
        if row is None:
            raise PlatformSenderEmailError("Sender not found", status_code=404)
        db.delete(row)
        db.commit()
