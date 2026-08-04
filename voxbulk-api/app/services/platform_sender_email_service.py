"""Platform sender emails (@voxbulk.com) — outbound From + optional SMTP password by purpose."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.encryption import get_encryptor
from app.models.platform_sender_email import SENDER_DOMAIN, PlatformSenderEmail

_LOCAL_RE = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,62}$", re.I)
_PURPOSE_RE = re.compile(r"^[a-z0-9_]{1,40}$", re.I)

# purpose → (local_part, from_name, notes)
SYSTEM_SENDERS: tuple[tuple[str, str, str, str], ...] = (
    ("sales", "sales", "Voxbulk Sales", "Hub invoices and sales mail"),
    ("billing", "billing", "VOXBULK Billing", "Billing and invoices"),
    ("careers", "careers", "VOXBULK Careers", "Interview / careers outbound"),
    ("support", "support", "VOXBULK Support", "Support outbound"),
    ("expo", "expo", "VOXBULK Expo", "Expo visitor / exhibitor mail"),
    ("survey_codes", "survey.codes", "VOXBULK Survey Codes", "Survey codes promo"),
    ("smart_card", "smartqr", "VOXBULK Smart Card QR", "Smart Card QR mail"),
    ("noreply", "noreply", "Voxbulk", "Transactional / system mail"),
)


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
            "smtp_username": getattr(row, "smtp_username", None) or "",
            "is_active": bool(row.is_active),
            "password_set": bool((getattr(row, "password_encrypted", None) or "").strip()),
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
            )
            .scalars()
            .all()
        )

    @staticmethod
    def get(db: Session, row_id: str) -> PlatformSenderEmail | None:
        return db.execute(
            select(PlatformSenderEmail).where(PlatformSenderEmail.id == row_id)
        ).scalar_one_or_none()

    @staticmethod
    def get_row_by_purpose(db: Session, purpose: str, *, active_only: bool = True) -> PlatformSenderEmail | None:
        key = PlatformSenderEmailService.normalize_purpose(purpose)
        if not key:
            return None
        q = select(PlatformSenderEmail).where(PlatformSenderEmail.purpose == key)
        if active_only:
            q = q.where(PlatformSenderEmail.is_active.is_(True))
        return db.execute(q).scalars().first()

    @staticmethod
    def get_sender_by_purpose(db: Session, purpose: str) -> tuple[str, str] | None:
        """Return (from_name, email) for an active row with this purpose, else None."""
        row = PlatformSenderEmailService.get_row_by_purpose(db, purpose)
        if row is None:
            return None
        return (row.from_name or row.local_part, row.email)

    @staticmethod
    def get_decrypted_password(db: Session, row: PlatformSenderEmail) -> str | None:
        raw = getattr(row, "password_encrypted", None)
        if not raw:
            return None
        try:
            return get_encryptor().decrypt_str(raw)
        except Exception:
            return None

    @staticmethod
    def resolve_outbound(db: Session, purpose: str) -> dict[str, str | None] | None:
        """
        Resolve From + optional SMTP auth for a purpose.
        Returns None if no active Emails row.
        Keys: from_name, from_email, smtp_username, smtp_password
        (smtp_* are None when password not set — caller uses platform SMTP login).
        """
        row = PlatformSenderEmailService.get_row_by_purpose(db, purpose)
        if row is None:
            return None
        pwd = PlatformSenderEmailService.get_decrypted_password(db, row)
        user = (getattr(row, "smtp_username", None) or "").strip() or row.email
        return {
            "from_name": row.from_name or row.local_part,
            "from_email": row.email,
            "smtp_username": user if pwd else None,
            "smtp_password": pwd,
        }

    @staticmethod
    def _set_password(row: PlatformSenderEmail, password: str | None) -> None:
        if password is None:
            return
        text = str(password).strip()
        if not text:
            return
        row.password_encrypted = get_encryptor().encrypt_str(text)

    @staticmethod
    def create(
        db: Session,
        *,
        local_part: str,
        from_name: str = "",
        purpose: str = "",
        notes: str | None = None,
        is_active: bool = True,
        smtp_username: str | None = None,
        password: str | None = None,
        commit: bool = True,
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
            smtp_username=(smtp_username or "").strip() or None,
            is_active=bool(is_active),
            notes=(notes or "").strip() or None,
            created_at=now,
            updated_at=now,
        )
        PlatformSenderEmailService._set_password(row, password)
        db.add(row)
        if commit:
            db.commit()
            db.refresh(row)
        else:
            db.flush()
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
        if "smtp_username" in patch:
            row.smtp_username = (str(patch["smtp_username"]).strip() if patch["smtp_username"] else None) or None
        if "notes" in patch:
            row.notes = (str(patch["notes"]).strip() if patch["notes"] is not None else None) or None
        if "is_active" in patch and patch["is_active"] is not None:
            row.is_active = bool(patch["is_active"])
        if "password" in patch and patch["password"] is not None and str(patch["password"]).strip():
            PlatformSenderEmailService._set_password(row, str(patch["password"]))
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

    @staticmethod
    def _copy_password_if_empty(row: PlatformSenderEmail, plain: str | None) -> None:
        if not plain or (getattr(row, "password_encrypted", None) or "").strip():
            return
        PlatformSenderEmailService._set_password(row, plain)

    @staticmethod
    def _upsert_system_row(
        db: Session,
        *,
        purpose: str,
        local_part: str,
        from_name: str,
        notes: str,
        mailbox_email: str | None = None,
        password_plain: str | None = None,
        smtp_username: str | None = None,
    ) -> PlatformSenderEmail:
        # Prefer existing by purpose, then by local_part
        row = PlatformSenderEmailService.get_row_by_purpose(db, purpose, active_only=False)
        if row is None:
            try:
                local = PlatformSenderEmailService.normalize_local_part(local_part)
            except PlatformSenderEmailError:
                local = local_part
            row = db.execute(
                select(PlatformSenderEmail).where(PlatformSenderEmail.local_part == local)
            ).scalar_one_or_none()
        if row is None and mailbox_email:
            try:
                local_from_mail = PlatformSenderEmailService.normalize_local_part(mailbox_email)
            except PlatformSenderEmailError:
                local_from_mail = None
            if local_from_mail:
                row = db.execute(
                    select(PlatformSenderEmail).where(PlatformSenderEmail.local_part == local_from_mail)
                ).scalar_one_or_none()
        if row is None:
            try:
                return PlatformSenderEmailService.create(
                    db,
                    local_part=local_part,
                    from_name=from_name,
                    purpose=purpose,
                    notes=notes,
                    smtp_username=smtp_username,
                    password=password_plain,
                    commit=False,
                )
            except PlatformSenderEmailError:
                # Race / clash — re-fetch
                row = PlatformSenderEmailService.get_row_by_purpose(db, purpose, active_only=False)
                if row is None:
                    raise
        # Update purpose / from_name if empty; never overwrite password already set
        if not (row.purpose or "").strip():
            row.purpose = purpose
        elif row.purpose != purpose and not PlatformSenderEmailService.get_row_by_purpose(db, purpose, active_only=False):
            row.purpose = purpose
        if from_name and not (row.from_name or "").strip():
            row.from_name = from_name
        if notes and not (row.notes or "").strip():
            row.notes = notes
        if smtp_username and not (getattr(row, "smtp_username", None) or "").strip():
            row.smtp_username = smtp_username
        if mailbox_email:
            try:
                new_local = PlatformSenderEmailService.normalize_local_part(mailbox_email)
                if new_local != row.local_part:
                    clash = db.execute(
                        select(PlatformSenderEmail).where(
                            PlatformSenderEmail.local_part == new_local,
                            PlatformSenderEmail.id != row.id,
                        )
                    ).scalar_one_or_none()
                    if clash is None:
                        row.local_part = new_local
            except PlatformSenderEmailError:
                pass
        PlatformSenderEmailService._copy_password_if_empty(row, password_plain)
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def ensure_system_senders(db: Session) -> list[PlatformSenderEmail]:
        """Seed system purposes and copy address/password from specialty mailboxes when missing."""
        copies: dict[str, dict[str, str | None]] = {}

        def _safe_mailbox(purpose: str, get_row, get_pwd, default_email: str, default_name: str) -> None:
            try:
                row = get_row(db)
                email = (getattr(row, "mailbox_email", None) or default_email).strip().lower()
                pwd = None
                try:
                    pwd = get_pwd(db)
                except Exception:
                    pwd = None
                user = (getattr(row, "smtp_username", None) or "").strip() or None
                copies[purpose] = {
                    "email": email,
                    "password": pwd,
                    "smtp_username": user,
                    "from_name": default_name,
                }
            except Exception:
                copies[purpose] = {
                    "email": default_email,
                    "password": None,
                    "smtp_username": None,
                    "from_name": default_name,
                }

        try:
            from app.services.billing_mailbox_settings_service import BillingMailboxSettingsService

            _safe_mailbox(
                "billing",
                BillingMailboxSettingsService.get_row,
                BillingMailboxSettingsService.get_decrypted_password,
                "billing@voxbulk.com",
                "VOXBULK Billing",
            )
        except Exception:
            pass
        try:
            from app.services.career_mailbox_settings_service import CareerMailboxSettingsService

            _safe_mailbox(
                "careers",
                CareerMailboxSettingsService.get_row,
                CareerMailboxSettingsService.get_decrypted_password,
                "careers@voxbulk.com",
                "VOXBULK Careers",
            )
        except Exception:
            pass
        try:
            from app.services.support_mailbox_settings_service import SupportMailboxSettingsService

            _safe_mailbox(
                "support",
                SupportMailboxSettingsService.get_row,
                SupportMailboxSettingsService.get_decrypted_password,
                "support@voxbulk.com",
                "VOXBULK Support",
            )
        except Exception:
            pass
        try:
            from app.services.expo.expo_mailbox_settings_service import ExpoMailboxSettingsService

            _safe_mailbox(
                "expo",
                ExpoMailboxSettingsService.get_row,
                getattr(ExpoMailboxSettingsService, "get_decrypted_password", lambda db: None),
                "expo@voxbulk.com",
                "VOXBULK Expo",
            )
        except Exception:
            pass
        try:
            from app.services.survey_codes_mailbox_settings_service import SurveyCodesMailboxSettingsService

            _safe_mailbox(
                "survey_codes",
                SurveyCodesMailboxSettingsService.get_row,
                SurveyCodesMailboxSettingsService.get_decrypted_password,
                "survey.codes@voxbulk.com",
                "VOXBULK Survey Codes",
            )
        except Exception:
            pass
        try:
            from app.services.smart_card.mailbox_settings_service import SmartCardMailboxSettingsService

            _safe_mailbox(
                "smart_card",
                SmartCardMailboxSettingsService.get_row,
                SmartCardMailboxSettingsService.get_decrypted_password,
                "smartqr@voxbulk.com",
                "VOXBULK Smart Card QR",
            )
        except Exception:
            pass

        # noreply: optionally copy platform SMTP from if it is @voxbulk.com
        try:
            from app.services.smtp_settings_service import SmtpSettingsService

            smtp = SmtpSettingsService.get_row(db)
            from_email = (smtp.from_email or "").strip().lower()
            if from_email.endswith(f"@{SENDER_DOMAIN}"):
                copies["noreply"] = {
                    "email": from_email,
                    "password": SmtpSettingsService.get_decrypted_password(db)
                    if from_email.startswith("noreply@")
                    else None,
                    "smtp_username": (smtp.username or "").strip() or None,
                    "from_name": (smtp.from_name or "Voxbulk").strip() or "Voxbulk",
                }
        except Exception:
            pass

        for purpose, local, name, notes in SYSTEM_SENDERS:
            meta = copies.get(purpose) or {}
            mailbox = meta.get("email") or f"{local}@{SENDER_DOMAIN}"
            try:
                PlatformSenderEmailService._upsert_system_row(
                    db,
                    purpose=purpose,
                    local_part=local,
                    from_name=str(meta.get("from_name") or name),
                    notes=notes,
                    mailbox_email=str(mailbox),
                    password_plain=meta.get("password"),  # type: ignore[arg-type]
                    smtp_username=meta.get("smtp_username"),  # type: ignore[arg-type]
                )
            except PlatformSenderEmailError:
                continue

        db.commit()
        return PlatformSenderEmailService.list_all(db)

    @staticmethod
    def test_send(db: Session, row_id: str, *, to_addr: str) -> dict[str, Any]:
        from app.services.smtp_mailer_service import SmtpMailerError, SmtpMailerService

        row = PlatformSenderEmailService.get(db, row_id)
        if row is None:
            raise PlatformSenderEmailError("Sender not found", status_code=404)
        if not row.is_active:
            raise PlatformSenderEmailError("Sender is frozen; unfreeze before testing")
        to_addr = (to_addr or "").strip()
        if not to_addr or "@" not in to_addr:
            raise PlatformSenderEmailError("Enter a valid test recipient email")
        pwd = PlatformSenderEmailService.get_decrypted_password(db, row)
        if not pwd:
            raise PlatformSenderEmailError(
                "Save a password on this email first (Edit → Password → Save), then Test again."
            )
        outbound = PlatformSenderEmailService.resolve_outbound(db, row.purpose) if row.purpose else None
        if outbound is None:
            # Allow test even without purpose using this row directly
            pwd = PlatformSenderEmailService.get_decrypted_password(db, row)
            outbound = {
                "from_name": row.from_name or row.local_part,
                "from_email": row.email,
                "smtp_username": ((row.smtp_username or "").strip() or row.email) if pwd else None,
                "smtp_password": pwd,
            }
        try:
            SmtpMailerService.send_plain(
                db,
                to_addr=to_addr,
                subject=f"VOXBULK / Emails hub test ({row.email})",
                body=(
                    f"This is a connectivity test from Messaging → Emails.\n\n"
                    f"From: {outbound['from_name']} <{outbound['from_email']}>\n"
                    f"Purpose: {row.purpose or '(none)'}\n"
                    f"Password on file: {'yes' if outbound.get('smtp_password') else 'no (using platform SMTP login)'}\n"
                ),
                from_email=outbound["from_email"],
                from_name=outbound["from_name"],
                smtp_username=outbound.get("smtp_username"),
                smtp_password=outbound.get("smtp_password"),
            )
        except SmtpMailerError as e:
            raise PlatformSenderEmailError(str(e)) from e
        return {"ok": True, "detail": f"Test email sent to {to_addr} from {outbound['from_email']}.", "from": outbound["from_email"], "to": to_addr}
