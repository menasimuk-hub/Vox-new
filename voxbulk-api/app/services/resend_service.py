from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


class ResendServiceError(RuntimeError):
    pass


class ResendService:
    @staticmethod
    def _headers(api_key: str) -> dict[str, str]:
        key = str(api_key or "").strip()
        if not key:
            raise ResendServiceError("Resend API key is required")
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    @staticmethod
    def test_connection(api_key: str, *, from_email: str, to_email: str) -> dict[str, Any]:
        from_addr = str(from_email or "").strip()
        to_addr = str(to_email or "").strip()
        if not from_addr or "@" not in from_addr:
            raise ResendServiceError("From email is required for Resend test")
        if not to_addr or "@" not in to_addr:
            raise ResendServiceError("Test recipient email is required")

        payload = {
            "from": from_addr,
            "to": [to_addr],
            "subject": "VoxBulk AI Team — Resend test",
            "text": "This is a test email from the VoxBulk AI Team sales agent settings.",
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(RESEND_API_URL, headers=ResendService._headers(api_key), json=payload)
        if resp.status_code == 401:
            raise ResendServiceError("Invalid Resend API key")
        if resp.status_code >= 400:
            raise ResendServiceError(f"Resend error ({resp.status_code}): {resp.text[:300]}")
        data = resp.json() if resp.content else {}
        return {"ok": True, "message": "Test email sent via Resend", "email_id": data.get("id")}

    @staticmethod
    def send_email(
        api_key: str,
        *,
        from_email: str,
        to_email: str,
        subject: str,
        text: str,
        html: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "text": text,
        }
        if html:
            payload["html"] = html
        if reply_to:
            payload["reply_to"] = reply_to

        with httpx.Client(timeout=45.0) as client:
            resp = client.post(RESEND_API_URL, headers=ResendService._headers(api_key), json=payload)
        if resp.status_code >= 400:
            raise ResendServiceError(f"Resend send failed ({resp.status_code}): {resp.text[:300]}")
        data = resp.json() if resp.content else {}
        return {"ok": True, "email_id": data.get("id")}
