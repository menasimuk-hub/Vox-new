from __future__ import annotations

import hashlib
import hmac


class MetaWebhookVerificationError(ValueError):
    pass


def verify_meta_webhook_signature(*, app_secret: str, raw_body: bytes, signature_header: str | None) -> None:
    secret = str(app_secret or "").strip()
    sig = str(signature_header or "").strip()
    if not secret:
        raise MetaWebhookVerificationError("Meta app secret is not configured")
    if not sig:
        raise MetaWebhookVerificationError("Missing X-Hub-Signature-256 header")
    if not sig.startswith("sha256="):
        raise MetaWebhookVerificationError("Invalid X-Hub-Signature-256 format")
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise MetaWebhookVerificationError("Invalid Meta webhook signature")
