"""Apply Telnyx Messaging Profile + webhook for the Yallasay line (SMS + WhatsApp)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from app.core.http_ssl import httpx_ssl_verify
from app.services.messaging_log_service import normalize_e164
from app.services.provider_settings import ProviderSettingsService
from app.services.telnyx_api_key import require_telnyx_api_key
from app.services.yallasay_telnyx_line import get_yallasay_line_config, persist_yallasay_profile_ids


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def apply_yallasay_line_telnyx_setup(db: Session) -> dict[str, Any]:
    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
    if not enabled:
        return {"ok": False, "error": "Telnyx integration is disabled"}
    config = ProviderSettingsService._validate_telnyx_config(cfg if isinstance(cfg, dict) else {})
    line = get_yallasay_line_config(db)
    phone = line.get("phone")
    if not phone:
        return {"ok": False, "error": "Set Yallasay line number (sms_from_2) in Admin and Save first."}

    profile_id = str(line.get("messaging_profile_id") or "").strip()
    webhook_url = str(line.get("messaging_webhook_url") or "").strip()
    if not webhook_url:
        base = str(config.get("webhook_base_url") or "").strip().rstrip("/")
        if base:
            webhook_url = f"{base}/telnyx/webhooks/messages"
    if not webhook_url:
        return {"ok": False, "error": "Set webhook base URL in Admin Telnyx settings."}

    try:
        api_key, _source = require_telnyx_api_key(db, config)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    warnings: list[str] = []
    with httpx.Client(timeout=30.0, verify=httpx_ssl_verify(), headers=_headers(api_key)) as client:
        if not profile_id:
            profiles_resp = client.get("https://api.telnyx.com/v2/messaging_profiles", params={"page[size]": 100})
            profiles_resp.raise_for_status()
            profiles = (profiles_resp.json().get("data") or []) if profiles_resp.headers.get("content-type", "").startswith("application/json") else []
            for row in profiles:
                if isinstance(row, dict) and str(row.get("name") or "").strip().lower() == "voxbulk-yallasay":
                    profile_id = str(row.get("id") or "").strip()
                    break
            if not profile_id:
                created = client.post(
                    "https://api.telnyx.com/v2/messaging_profiles",
                    json={
                        "name": "voxbulk-yallasay",
                        "webhook_url": webhook_url,
                        "webhook_api_version": "2",
                        "enabled": True,
                    },
                )
                created.raise_for_status()
                profile_id = str((created.json().get("data") or {}).get("id") or "").strip()
                warnings.append(f"Created messaging profile voxbulk-yallasay ({profile_id})")
        else:
            client.patch(
                f"https://api.telnyx.com/v2/messaging_profiles/{profile_id}",
                json={"webhook_url": webhook_url, "webhook_api_version": "2"},
            ).raise_for_status()

        try:
            client.patch(
                f"https://api.telnyx.com/v2/messaging_phone_numbers/{quote(phone, safe='')}",
                json={"messaging_profile_id": profile_id},
            ).raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            warnings.append(
                f"Could not assign profile to {phone} via messaging_phone_numbers (HTTP {status}). "
                "Profile UUID was still saved — WhatsApp may use WABA linkage instead."
            )
        except Exception as exc:
            warnings.append(f"Could not assign profile to {phone}: {exc}")

        probe = httpx.get(webhook_url, timeout=15.0, verify=httpx_ssl_verify())
        webhook_ok = probe.status_code < 400

    if profile_id:
        persist_yallasay_profile_ids(db, profile_id, phone=phone)

    return {
        "ok": True,
        "phone": phone,
        "messaging_profile_id": profile_id,
        "messaging_webhook_url": webhook_url,
        "webhook_probe_status": probe.status_code,
        "webhook_probe_ok": webhook_ok,
        "warnings": warnings,
        "next_steps": [
            "Reply SMS to the Yallasay number — appears in Admin → Messages (Abuu does not reply by SMS).",
            "For WhatsApp: link the same number in Telnyx → WhatsApp → WABA and set WABA webhook to the same URL.",
            "Message Abuu on WhatsApp — replies go out on WhatsApp only.",
        ],
    }
