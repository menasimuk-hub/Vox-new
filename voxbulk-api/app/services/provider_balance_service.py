from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.http_ssl import httpx_ssl_verify
from app.services.providers.elevenlabs_service import ElevenLabsProviderService
from app.services.telnyx_api_key import require_telnyx_api_key


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_telnyx_balance(db: Session) -> dict[str, Any]:
    try:
        api_key, key_source = require_telnyx_api_key(db)
    except ValueError as exc:
        return {
            "configured": False,
            "ok": False,
            "label": "Telnyx",
            "message": str(exc),
        }

    try:
        response = httpx.get(
            "https://api.telnyx.com/v2/balance",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            timeout=20.0,
            verify=httpx_ssl_verify(),
        )
    except Exception as exc:
        return {
            "configured": True,
            "ok": False,
            "label": "Telnyx",
            "message": f"Telnyx balance request failed: {exc}",
            "key_source": key_source,
        }

    if response.status_code == 401:
        return {
            "configured": True,
            "ok": False,
            "label": "Telnyx",
            "message": "Telnyx API key rejected — check Integrations → Telnyx.",
            "key_source": key_source,
        }

    if not response.is_success:
        detail = (response.text or "")[:240]
        return {
            "configured": True,
            "ok": False,
            "label": "Telnyx",
            "message": f"Telnyx returned {response.status_code}" + (f" — {detail}" if detail else ""),
            "key_source": key_source,
        }

    body = response.json()
    data = body.get("data") if isinstance(body, dict) else {}
    if not isinstance(data, dict):
        data = {}

    currency = str(data.get("currency") or "USD").upper()
    balance = _safe_float(data.get("balance"))
    available = _safe_float(data.get("available_credit"))
    pending = _safe_float(data.get("pending")) or 0.0
    credit_limit = _safe_float(data.get("credit_limit")) or 0.0
    amount = available if available is not None else balance

    return {
        "configured": True,
        "ok": True,
        "label": "Telnyx",
        "currency": currency,
        "balance": balance,
        "available_credit": available,
        "pending": pending,
        "credit_limit": credit_limit,
        "amount": amount,
        "key_source": key_source,
    }


def fetch_elevenlabs_balance(db: Session) -> dict[str, Any]:
    try:
        config = ElevenLabsProviderService._config(db)
    except ValueError as exc:
        return {
            "configured": False,
            "ok": False,
            "label": "ElevenLabs",
            "message": str(exc),
        }

    base_url = str(config.get("base_url") or "https://api.elevenlabs.io").rstrip("/")
    api_key = str(config.get("api_key") or "").strip()
    headers = {"xi-api-key": api_key, "Accept": "application/json"}

    try:
        response = httpx.get(
            f"{base_url}/v1/user",
            headers=headers,
            timeout=20.0,
            verify=ElevenLabsProviderService._ssl_context(),
        )
    except Exception as exc:
        return {
            "configured": True,
            "ok": False,
            "label": "ElevenLabs",
            "message": f"ElevenLabs balance request failed: {exc}",
        }

    if response.status_code == 401:
        try:
            detail = response.json()
        except Exception:
            detail = {}
        missing_perm = ""
        if isinstance(detail, dict):
            inner = detail.get("detail")
            if isinstance(inner, dict) and "user_read" in str(inner.get("message") or ""):
                missing_perm = " Enable the user_read permission on your ElevenLabs API key."
        return {
            "configured": True,
            "ok": False,
            "label": "ElevenLabs",
            "message": f"ElevenLabs API key cannot read account balance.{missing_perm}",
        }

    if not response.is_success:
        detail = (response.text or "")[:240]
        return {
            "configured": True,
            "ok": False,
            "label": "ElevenLabs",
            "message": f"ElevenLabs returned {response.status_code}" + (f" — {detail}" if detail else ""),
        }

    body = response.json()
    subscription = body.get("subscription") if isinstance(body, dict) else {}
    if not isinstance(subscription, dict):
        subscription = {}

    character_count = int(subscription.get("character_count") or 0)
    character_limit = int(subscription.get("character_limit") or 0)
    remaining = max(0, character_limit - character_count)
    tier = str(subscription.get("tier") or "").strip() or "unknown"
    status = str(subscription.get("status") or "").strip() or "unknown"
    currency = str(subscription.get("currency") or "").upper() or None

    overage = subscription.get("current_overage")
    overage_amount = None
    overage_currency = currency
    if isinstance(overage, dict):
        overage_amount = _safe_float(overage.get("amount"))
        overage_currency = str(overage.get("currency") or overage_currency or "").upper() or overage_currency

    return {
        "configured": True,
        "ok": True,
        "label": "ElevenLabs",
        "tier": tier,
        "status": status,
        "currency": currency,
        "character_count": character_count,
        "character_limit": character_limit,
        "characters_remaining": remaining,
        "overage_amount": overage_amount,
        "overage_currency": overage_currency,
    }


def get_provider_balances(db: Session) -> dict[str, Any]:
    return {
        "telnyx": fetch_telnyx_balance(db),
        "elevenlabs": fetch_elevenlabs_balance(db),
    }
