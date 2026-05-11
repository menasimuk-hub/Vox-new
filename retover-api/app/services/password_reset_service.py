from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.services.transactional_email_service import TransactionalEmailService

logger = logging.getLogger(__name__)


def reset_token_hmac(raw_token: str) -> str:
    key = get_settings().jwt_secret_key.encode("utf-8")
    return hmac.new(key, raw_token.encode("utf-8"), hashlib.sha256).hexdigest()


class PasswordResetService:
    @staticmethod
    def request_reset(db: Session, *, email: str) -> None:
        """Create token when user qualifies; send email on a fresh session after commit."""
        normalized = (email or "").strip().lower()
        if not normalized:
            return

        user = db.execute(select(User).where(User.email == normalized)).scalar_one_or_none()
        if user is None or not user.is_active:
            return
        if not user.password_hash:
            return

        db.execute(
            delete(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
        )

        raw = secrets.token_urlsafe(32)
        hmac_hex = reset_token_hmac(raw)
        settings = get_settings()
        minutes = max(5, int(settings.password_reset_token_expire_minutes or 60))
        expires = datetime.utcnow() + timedelta(minutes=minutes)

        db.add(PasswordResetToken(user_id=user.id, token_hmac=hmac_hex, expires_at=expires))
        db.commit()

        base = settings.public_app_origin.rstrip("/")
        reset_url = f"{base}/reset-password?token={raw}"
        recipient = user.email
        vars_ = {"reset_url": reset_url, "reset_link": reset_url, "user_email": normalized}

        try:
            with get_sessionmaker()() as s2:
                sent, err = TransactionalEmailService.send_templated_optional(
                    s2, template_key="forgot_password", to_email=recipient, variables=vars_
                )
                if not sent and err and err not in ("unknown_template", None):
                    logger.warning("password_reset_mail_failed", extra={"err": err})
        except Exception:
            logger.exception("password_reset_mail_exception")

    @staticmethod
    def consume_reset(db: Session, *, raw_token: str, new_password: str) -> tuple[bool, str]:
        raw = str(raw_token or "").strip()
        pwd = str(new_password or "")
        if len(raw) < 10:
            return False, "Invalid or expired reset link. Request a new one from the sign-in page."
        if len(pwd) < 6:
            return False, "Password must be at least 6 characters."

        h = reset_token_hmac(raw)
        tok = db.execute(select(PasswordResetToken).where(PasswordResetToken.token_hmac == h)).scalar_one_or_none()
        now = datetime.utcnow()
        if tok is None or tok.used_at is not None or tok.expires_at < now:
            return False, "Invalid or expired reset link. Request a new one from the sign-in page."

        user = db.execute(select(User).where(User.id == tok.user_id)).scalar_one_or_none()
        if user is None:
            return False, "Invalid or expired reset link. Request a new one from the sign-in page."
        if not user.is_active:
            return False, "Account is inactive. Contact support."

        user.password_hash = hash_password(pwd)
        tok.used_at = now
        db.add(user)
        db.add(tok)
        db.flush()

        db.execute(
            delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        )

        db.commit()
        return True, "Password updated. You can sign in with your new password."
