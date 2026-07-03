from __future__ import annotations

import hashlib
import hmac

import pytest

from app.services.meta_webhook_security import MetaWebhookVerificationError, verify_meta_webhook_signature


def test_verify_meta_webhook_signature_ok():
    body = b'{"object":"whatsapp_business_account"}'
    secret = "test_secret"
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    verify_meta_webhook_signature(app_secret=secret, raw_body=body, signature_header=sig)


def test_verify_meta_webhook_signature_bad():
    body = b'{"object":"whatsapp_business_account"}'
    with pytest.raises(MetaWebhookVerificationError):
        verify_meta_webhook_signature(
            app_secret="test_secret",
            raw_body=body,
            signature_header="sha256=deadbeef",
        )
