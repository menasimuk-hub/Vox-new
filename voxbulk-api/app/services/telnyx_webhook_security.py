"""Optional Telnyx webhook signature verification (Ed25519)."""

from __future__ import annotations

import base64
import logging
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.core.config import get_settings

logger = logging.getLogger(__name__)
LOG_PREFIX = "[telnyx-webhook-verify]"


class TelnyxWebhookVerificationError(ValueError):
    pass


def verify_telnyx_webhook(
    raw_body: bytes,
    *,
    signature_header: str | None,
    timestamp_header: str | None,
) -> bool:
    """
    Verify Telnyx Ed25519 webhook signature when TELNYX_WEBHOOK_PUBLIC_KEY is configured.
    Returns True when verification passes or is skipped (no public key configured).
    """
    public_key_b64 = str(get_settings().telnyx_webhook_public_key or "").strip()
    if not public_key_b64:
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
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
        public_key.verify(base64.b64decode(signature_header), signed_payload)
    except (InvalidSignature, ValueError) as exc:
        logger.warning("%s failed_invalid_signature err=%s", LOG_PREFIX, exc)
        raise TelnyxWebhookVerificationError("Invalid Telnyx webhook signature") from exc

    logger.info("%s passed timestamp=%s", LOG_PREFIX, timestamp_header)
    return True
