"""Platform-admin TOTP (is_superuser only). Secret is Fernet-encrypted at rest."""

from __future__ import annotations

import pyotp

from app.core.encryption import get_encryptor
from app.models.user import User

ISSUER = "VOXBULK Admin"


def _decrypt_secret(user: User) -> str | None:
    raw = str(getattr(user, "mfa_totp_secret", None) or "").strip()
    if not raw:
        return None
    return get_encryptor().decrypt_str(raw)


def mfa_enabled(user: User) -> bool:
    return bool(getattr(user, "is_superuser", False) and getattr(user, "mfa_enabled", False) and _decrypt_secret(user))


def verify_totp(user: User, code: str) -> bool:
    secret = _decrypt_secret(user)
    if not secret:
        return False
    totp = pyotp.TOTP(secret)
    return bool(totp.verify(str(code or "").strip().replace(" ", ""), valid_window=1))


def start_setup(user: User) -> dict:
    if not user.is_superuser:
        raise PermissionError("MFA is only available for platform admins")
    secret = pyotp.random_base32()
    user.mfa_totp_secret = get_encryptor().encrypt_str(secret)
    user.mfa_enabled = False
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=ISSUER)
    return {"otpauth_uri": uri, "secret": secret, "enabled": False}


def enable(user: User, code: str) -> None:
    if not user.is_superuser:
        raise PermissionError("MFA is only available for platform admins")
    if not verify_totp(user, code):
        raise ValueError("Invalid authenticator code")
    user.mfa_enabled = True


def disable(user: User, code: str) -> None:
    if not verify_totp(user, code):
        raise ValueError("Invalid authenticator code")
    user.mfa_enabled = False
    user.mfa_totp_secret = None
