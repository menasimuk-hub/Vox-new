#!/usr/bin/env python3
"""Configure Telnyx SMS for VoxBulk inbound (Meta verification codes, Admin Refresh inbound).

Usage (dry-run — shows plan only):
  cd voxbulk-api
  set TELNYX_API_KEY=KEYxxxxxxxx
  python scripts/telnyx_sms_setup.py --phone +447700900123

Apply changes (messaging profile webhook + assign number):
  python scripts/telnyx_sms_setup.py --phone +447700900123 --apply

List account numbers and profiles:
  python scripts/telnyx_sms_setup.py --list

Optional:
  --webhook-base https://api.voxbulk.com   (default)
  --profile-id UUID                        (reuse profile; else pick/create voxbulk-sms)
  --profile-name voxbulk-sms               (name when creating a profile)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.http_ssl import httpx_ssl_verify
from app.services.messaging_log_service import normalize_e164


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _get(client: httpx.Client, path: str, **params: Any) -> dict[str, Any]:
    response = client.get(f"https://api.telnyx.com/v2{path}", params=params or None)
    response.raise_for_status()
    body = response.json()
    return body if isinstance(body, dict) else {}


def _patch(client: httpx.Client, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.patch(f"https://api.telnyx.com/v2{path}", json=payload)
    response.raise_for_status()
    body = response.json()
    return body if isinstance(body, dict) else {}


def _post(client: httpx.Client, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post(f"https://api.telnyx.com/v2{path}", json=payload)
    response.raise_for_status()
    body = response.json()
    return body if isinstance(body, dict) else {}


def list_messaging_profiles(client: httpx.Client) -> list[dict[str, Any]]:
    body = _get(client, "/messaging_profiles", **{"page[size]": 100})
    rows = body.get("data") or []
    return [r for r in rows if isinstance(r, dict)]


def list_phone_numbers(client: httpx.Client) -> list[dict[str, Any]]:
    body = _get(client, "/phone_numbers", **{"page[size]": 250})
    rows = body.get("data") or []
    return [r for r in rows if isinstance(r, dict)]


def get_messaging_phone_number(client: httpx.Client, phone: str) -> dict[str, Any] | None:
    encoded = quote(phone, safe="")
    try:
        body = _get(client, f"/messaging_phone_numbers/{encoded}")
        data = body.get("data")
        return data if isinstance(data, dict) else None
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        raise


def ensure_profile(
    client: httpx.Client,
    *,
    webhook_url: str,
    profile_id: str | None,
    profile_name: str,
) -> dict[str, Any]:
    profiles = list_messaging_profiles(client)
    if profile_id:
        for row in profiles:
            if str(row.get("id") or "") == profile_id:
                return row
        raise SystemExit(f"Messaging profile not found: {profile_id}")

    for row in profiles:
        if str(row.get("name") or "").strip().lower() == profile_name.strip().lower():
            return row

    return {"id": None, "name": profile_name, "_create": True, "webhook_url": webhook_url}


def cmd_list(client: httpx.Client) -> int:
    print("=== Messaging profiles ===")
    for row in list_messaging_profiles(client):
        print(
            f"  {row.get('id')}  {row.get('name')}  webhook={row.get('webhook_url') or '(none)'}"
        )
    print("\n=== Phone numbers ===")
    for row in list_phone_numbers(client):
        pn = row.get("phone_number") or ""
        caps = row.get("features") or row.get("messaging_product") or ""
        print(f"  {pn}  id={row.get('id')}  features={caps}")
        if pn:
            msg = get_messaging_phone_number(client, str(pn))
            if msg:
                print(f"    messaging_profile_id={msg.get('messaging_profile_id')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure Telnyx SMS webhook + number for VoxBulk")
    parser.add_argument("--api-key", default=os.environ.get("TELNYX_API_KEY", "").strip())
    parser.add_argument("--phone", help="E.164 SMS number to assign (e.g. +447700900123)")
    parser.add_argument("--webhook-base", default="https://api.voxbulk.com", help="VoxBulk API public base URL")
    parser.add_argument("--profile-id", help="Existing messaging profile UUID")
    parser.add_argument("--profile-name", default="voxbulk-sms", help="Profile name when creating new")
    parser.add_argument("--list", action="store_true", help="List numbers and profiles only")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run)")
    args = parser.parse_args()

    api_key = str(args.api_key or "").strip()
    if not api_key:
        print("Set TELNYX_API_KEY or pass --api-key", file=sys.stderr)
        return 1

    webhook_url = f"{args.webhook_base.rstrip('/')}/telnyx/webhooks/messages"

    with httpx.Client(timeout=30.0, verify=httpx_ssl_verify(), headers=_headers(api_key)) as client:
        if args.list:
            return cmd_list(client)

        if not args.phone:
            print("Pass --phone +E164 or use --list", file=sys.stderr)
            return 1

        try:
            phone = normalize_e164(args.phone.strip())
        except ValueError as exc:
            print(f"Invalid phone: {exc}", file=sys.stderr)
            return 1

        account_numbers = [str(r.get("phone_number") or "") for r in list_phone_numbers(client)]
        if account_numbers and phone not in account_numbers:
            print(f"Warning: {phone} not in Telnyx account numbers: {', '.join(account_numbers[:10])}")

        profile = ensure_profile(
            client,
            webhook_url=webhook_url,
            profile_id=(args.profile_id or "").strip() or None,
            profile_name=args.profile_name,
        )
        profile_id = str(profile.get("id") or "").strip()

        plan = {
            "phone": phone,
            "webhook_url": webhook_url,
            "messaging_profile_id": profile_id or f"(create '{args.profile_name}')",
            "admin_sms_from": phone,
            "admin_webhook_base": args.webhook_base.rstrip("/"),
        }
        print("Plan:")
        print(json.dumps(plan, indent=2))

        print("\nAdmin → Integrations → Telnyx — set after Telnyx apply:")
        print(f"  SMS number:              {phone}")
        print(f"  SMS messaging profile:   {profile_id or '(see output after --apply)'}")
        print(f"  Webhook base URL:        {args.webhook_base.rstrip('/')}")

        if not args.apply:
            print("\nDry-run only. Re-run with --apply to configure Telnyx.")
            return 0

        if profile.get("_create"):
            created = _post(
                client,
                "/messaging_profiles",
                {
                    "name": args.profile_name,
                    "webhook_url": webhook_url,
                    "webhook_api_version": "2",
                    "enabled": True,
                },
            )
            profile_id = str((created.get("data") or {}).get("id") or "").strip()
            if not profile_id:
                print("Failed to create messaging profile", file=sys.stderr)
                return 1
            print(f"Created messaging profile: {profile_id}")
        else:
            _patch(client, f"/messaging_profiles/{profile_id}", {"webhook_url": webhook_url, "webhook_api_version": "2"})
            print(f"Updated profile webhook: {profile_id}")

        _patch(
            client,
            f"/messaging_phone_numbers/{quote(phone, safe='')}",
            {"messaging_profile_id": profile_id},
        )
        print(f"Assigned {phone} → profile {profile_id}")

        try:
            probe = httpx.get(webhook_url, timeout=15.0, verify=httpx_ssl_verify())
            print(f"Webhook probe {webhook_url} → HTTP {probe.status_code}")
            if probe.status_code >= 400:
                print("Warning: webhook did not return 200 — fix nginx/API before expecting inbound SMS.")
        except Exception as exc:
            print(f"Webhook probe failed: {exc}")

        print("\nNext steps:")
        print("  1. Save the three Admin fields above → Save Telnyx")
        print("  2. Admin → Test SMS to your mobile")
        print("  3. Reply or trigger Meta verification → Refresh inbound")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
