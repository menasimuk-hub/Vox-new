"""Telnyx webhook signature verification (Ed25519).

Fails closed in production/staging when no public key is configured.
In local/dev/test, verification is skipped only when the key is unset
(so unit tests and local stacks without Telnyx signing still work).
"""

from __future__ import annotations

import base64
import logging
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy.orm import Session

from app.core.config import get_settings

logger = logging.getLogger(__name__)
LOG_PREFIX = "[telnyx-webhook-verify]"


class TelnyxWebhookVerificationError(ValueError):
    pass


def webhook_signature_required() -> bool:
    """True when missing/invalid signatures must reject the request."""
    env = str(get_settings().env or "").lower().strip()
    return env not in {"dev", "development", "local", "test", "testing"}


def resolve_telnyx_webhook_public_key(db: Session | None = None) -> str:
    """Prefer env TELNYX_WEBHOOK_PUBLIC_KEY; else Admin Telnyx config webhook_public_key."""
    env_key = str(get_settings().telnyx_webhook_public_key or "").strip()
    if env_key:
        return env_key
    if db is None:
        return ""
    try:
        from app.services.provider_settings import ProviderSettingsService

        cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
        if isinstance(cfg, dict):
            return str(cfg.get("webhook_public_key") or "").strip()
    except Exception:
        logger.debug("%s admin_key_lookup_failed", LOG_PREFIX, exc_info=True)
    return ""


def verify_telnyx_webhook(
    raw_body: bytes,
    *,
    signature_header: str | None,
    timestamp_header: str | None,
    db: Session | None = None,
    public_key_b64: str | None = None,
) -> bool:
    """
    Verify Telnyx Ed25519 webhook signature.

    - Production/staging: public key required; missing key or bad signature → error.
    - Dev/test: if no public key configured, skip verify (return True).
    """
    key = (public_key_b64 if public_key_b64 is not None else resolve_telnyx_webhook_public_key(db)).strip()
    if not key:
        if webhook_signature_required():
            logger.warning("%s failed_no_public_key", LOG_PREFIX)
            raise TelnyxWebhookVerificationError("Telnyx webhook public key is not configured")
        logger.debug("%s skipped_no_public_key", LOG_PREFIX)
        return True

    if not signature_header or not timestamp_header:
        logger.warning("%s failed_missing_headers", LOG_PREFIX)
        raise TelnyxWebhookVerificationError("Missing Telnyx signature headers")

    try:
        ts = int(str(timestamp_header).strip())
    except ValueError as exc:
        raise TelnyxWebhookVerificationError("Invalid telnyx-timestamp") from exc

    age = abs(int(time.time()) - ts)
    if age > 300:
        raise TelnyxWebhookVerificationError("Telnyx webhook timestamp too old")

    signed_payload = f"{timestamp_header}|".encode("utf-8") + raw_body
    try:
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(key))
        public_key.verify(base64.b64decode(signature_header), signed_payload)
    except (InvalidSignature, ValueError) as exc:
        logger.warning("%s failed_invalid_signature err=%s", LOG_PREFIX, exc)
        raise TelnyxWebhookVerificationError("Invalid Telnyx webhook signature") from exc

    logger.info("%s passed timestamp=%s", LOG_PREFIX, timestamp_header)
    return True
