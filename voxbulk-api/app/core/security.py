from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import base64
import hashlib
import hmac
from urllib.parse import urlencode

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings


# Password hashing (deterministic)
# We intentionally standardize on pbkdf2_sha256 for now to avoid bcrypt backend
# instability on some Windows/Python builds. Revisit before production if you
# require bcrypt/argon2.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    *,
    subject: str,
    org_id: str,
    expires_minutes: int | None = None,
    token_version: int = 0,
) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes if expires_minutes is not None else settings.access_token_expire_minutes
    )

    to_encode: dict[str, Any] = {
        "sub": subject,
        "org_id": org_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
        "tv": int(token_version or 0),
    }
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError as e:
        raise ValueError("Invalid token") from e


def compute_hmac_sha256_base64(*, secret: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(mac).decode("ascii")


def verify_hmac_sha256_base64(*, secret: str, body: bytes, signature_b64: str) -> bool:
    if not secret:
        return False
    expected = compute_hmac_sha256_base64(secret=secret, body=body)
    return hmac.compare_digest(expected, signature_b64)


def compute_twilio_signature(*, auth_token: str, url: str, params: dict[str, str]) -> str:
    """
    Twilio Request Validation (classic form/webhook signature).

    Signature = Base64( HMAC-SHA1( auth_token, url + concat(sorted(params)) ) )
    where concat(sorted(params)) is key1 + value1 + key2 + value2 ... sorted by key.
    """
    s = url
    for k in sorted(params.keys()):
        s += k + params[k]
    mac = hmac.new(auth_token.encode("utf-8"), s.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(mac).decode("ascii")


def verify_twilio_signature(*, auth_token: str, url: str, params: dict[str, str], signature: str) -> bool:
    if not auth_token:
        return False
    expected = compute_twilio_signature(auth_token=auth_token, url=url, params=params)
    return hmac.compare_digest(expected, signature)


def compute_gocardless_signature_hex(*, secret: str, body: bytes) -> str:
    """GoCardless: hex-encoded HMAC-SHA256 over raw request body."""
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return mac


def verify_gocardless_signature_hex(*, secret: str, body: bytes, signature_hex: str) -> bool:
    if not secret:
        return False
    expected = compute_gocardless_signature_hex(secret=secret, body=body)
    return hmac.compare_digest(expected, signature_hex)
