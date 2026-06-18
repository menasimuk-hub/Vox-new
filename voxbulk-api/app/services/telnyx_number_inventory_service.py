"""Telnyx account number inventory and configured-sender validation."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from app.services.telnyx_api_key import normalize_telnyx_e164
from app.services.telnyx_number_routing_service import normalize_route_list, seed_routes_from_legacy
from app.core.http_ssl import httpx_ssl_verify


def _telnyx_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def list_account_phone_records(*, api_key: str) -> list[dict[str, Any]]:
    """Fetch all phone number records from Telnyx (paginated)."""
    records: list[dict[str, Any]] = []
    page = 1
    with httpx.Client(timeout=25.0, verify=httpx_ssl_verify()) as client:
        while True:
            response = client.get(
                "https://api.telnyx.com/v2/phone_numbers",
                headers=_telnyx_headers(api_key),
                params={"page[size]": 250, "page[number]": page},
            )
            response.raise_for_status()
            body = response.json()
            batch = body.get("data") or []
            if not isinstance(batch, list):
                break
            for row in batch:
                if isinstance(row, dict):
                    records.append(row)
            meta = body.get("meta") or {}
            total_pages = int(meta.get("total_pages") or 1)
            if page >= total_pages or not batch:
                break
            page += 1
    return records


def _messaging_profile_for_number(*, api_key: str, phone: str) -> str | None:
    encoded = quote(phone, safe="")
    try:
        with httpx.Client(timeout=12.0, verify=httpx_ssl_verify()) as client:
            response = client.get(
                f"https://api.telnyx.com/v2/messaging_phone_numbers/{encoded}",
                headers=_telnyx_headers(api_key),
            )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json().get("data")
        if isinstance(data, dict):
            pid = str(data.get("messaging_profile_id") or "").strip()
            return pid or None
    except Exception:
        return None
    return None


def _collect_configured_senders(config: dict[str, Any]) -> list[dict[str, Any]]:
    cfg = seed_routes_from_legacy(config)
    senders: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(number: str, role: str, label: str = "") -> None:
        raw = str(number or "").strip()
        if not raw:
            return
        try:
            e164 = normalize_telnyx_e164(raw)
        except ValueError:
            e164 = raw
        key = (e164, role)
        if key in seen:
            return
        seen.add(key)
        senders.append({"number": e164, "role": role, "label": str(label or "").strip()})

    for row in normalize_route_list(cfg.get("voice_routes")):
        add(row["number"], "voice", row.get("label") or "")
    for row in normalize_route_list(cfg.get("whatsapp_routes")):
        add(row["number"], "whatsapp", row.get("label") or "")
    add(str(cfg.get("sms_from") or "").strip(), "sms", "SMS")
    add(str(cfg.get("default_outbound_number") or cfg.get("from_phone_number") or "").strip(), "voice", "Default voice")
    add(str(cfg.get("whatsapp_from") or "").strip(), "whatsapp", "Default WhatsApp")
    return senders


def build_number_inventory(*, api_key: str, config: dict[str, Any]) -> dict[str, Any]:
    """Compare configured senders against Telnyx account numbers."""
    connection_id = str(config.get("connection_id") or config.get("voice_api_application_id") or "").strip()
    sms_profile_id = str(config.get("messaging_profile_id") or "").strip()
    wa_profile_id = str(config.get("whatsapp_messaging_profile_id") or "").strip() or sms_profile_id

    try:
        records = list_account_phone_records(api_key=api_key)
    except Exception as exc:
        return {
            "ok": False,
            "account_inventory": [],
            "configured_checks": [],
            "telnyx_phone_numbers": [],
            "inventory_error": str(exc)[:300],
        }

    by_number: dict[str, dict[str, Any]] = {}
    account_inventory: list[dict[str, Any]] = []
    account_numbers: list[str] = []

    for row in records:
        pn = str(row.get("phone_number") or "").strip()
        if not pn:
            continue
        try:
            pn = normalize_telnyx_e164(pn)
        except ValueError:
            pass
        conn = str(row.get("connection_id") or "").strip()
        msg_profile = _messaging_profile_for_number(api_key=api_key, phone=pn)
        entry = {
            "number": pn,
            "telnyx_id": str(row.get("id") or "").strip() or None,
            "connection_id": conn or None,
            "messaging_profile_id": msg_profile,
            "on_account": True,
        }
        by_number[pn] = entry
        account_inventory.append(entry)
        account_numbers.append(pn)

    configured = _collect_configured_senders(config)
    configured_checks: list[dict[str, Any]] = []
    configured_set: set[str] = set()
    inventory_warnings: list[str] = []

    for sender in configured:
        num = sender["number"]
        role = sender["role"]
        configured_set.add(num)
        inv = by_number.get(num)
        on_account = inv is not None
        connection_ok: bool | None = None
        messaging_profile_ok: bool | None = None
        issues: list[str] = []

        if not on_account:
            issues.append("not on Telnyx account")
        elif role == "voice" and connection_id:
            conn = str(inv.get("connection_id") or "").strip()
            if conn and conn != connection_id:
                connection_ok = False
                issues.append(f"connection mismatch (number on {conn[:8]}…, expected {connection_id[:8]}…)")
            elif conn:
                connection_ok = True
            else:
                connection_ok = None
        elif role in ("sms", "whatsapp") and inv:
            expected_profile = wa_profile_id if role == "whatsapp" else sms_profile_id
            actual = str(inv.get("messaging_profile_id") or "").strip()
            if expected_profile and actual and actual != expected_profile:
                messaging_profile_ok = False
                issues.append("messaging profile mismatch")
            elif expected_profile and actual:
                messaging_profile_ok = True
            elif expected_profile and not actual:
                messaging_profile_ok = False
                issues.append("not on a messaging profile")

        status = "ok" if on_account and not issues else ("warn" if on_account else "error")
        configured_checks.append(
            {
                "number": num,
                "role": role,
                "label": sender.get("label") or "",
                "on_account": on_account,
                "connection_ok": connection_ok,
                "messaging_profile_ok": messaging_profile_ok,
                "status": status,
                "issues": issues,
            }
        )

    for num in account_numbers:
        if num not in configured_set:
            inventory_warnings.append(f"{num} on Telnyx account but not assigned to any route")

    all_ok = all(c["status"] == "ok" for c in configured_checks) if configured_checks else True
    return {
        "ok": all_ok,
        "account_inventory": account_inventory,
        "configured_checks": configured_checks,
        "telnyx_phone_numbers": account_numbers,
        "inventory_warnings": inventory_warnings,
    }
