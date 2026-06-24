#!/usr/bin/env python3
"""Seed HubSpot appointment test data for VoxBulk.

What this script does:
1) Ensures a contact datetime property exists (default: appointment_date)
2) Ensures a static HubSpot list exists (default: VoxBulk · Appointment test)
3) Upserts contacts with phone + appointment datetime
4) Adds those contacts to the static list

Usage:
  cd voxbulk-api
  python scripts/seed_hubspot_appointment_test_data.py --token <HUBSPOT_TOKEN>

  HUBSPOT_ACCESS_TOKEN=... python scripts/seed_hubspot_appointment_test_data.py \
    --base-email you@gmail.com --count 12 --list-name "VoxBulk · Appointments"
"""

from __future__ import annotations

import argparse
import os
import random
import string
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

HUBSPOT_API = "https://api.hubapi.com"
CONTACTS_BATCH_UPSERT = f"{HUBSPOT_API}/crm/v3/objects/contacts/batch/upsert"
CONTACTS_SEARCH = f"{HUBSPOT_API}/crm/v3/objects/contacts/search"
PROPERTIES_BASE = f"{HUBSPOT_API}/crm/v3/properties/0-1"
LISTS_SEARCH = f"{HUBSPOT_API}/crm/v3/lists/search"
LISTS_BASE = f"{HUBSPOT_API}/crm/v3/lists"


class HubspotSeedError(Exception):
    pass


@dataclass
class ContactSeedRow:
    email: str
    first_name: str
    last_name: str
    phone: str
    appointment_iso: str
    service_type: str
    branch: str


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _raise_for_status(res: httpx.Response, *, action: str) -> None:
    if res.status_code >= 400:
        raise HubspotSeedError(f"{action} failed ({res.status_code}): {res.text[:300]}")


def _safe_slug(raw: str) -> str:
    out = []
    for ch in raw.lower():
        if ch.isalnum():
            out.append(ch)
        else:
            out.append("_")
    cleaned = "".join(out).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned[:40] or "appointment_date"


def _ensure_property(
    client: httpx.Client,
    token: str,
    *,
    property_name: str,
    property_label: str,
) -> None:
    get_res = client.get(f"{PROPERTIES_BASE}/{property_name}", headers=_headers(token))
    if get_res.status_code == 200:
        print(f"[ok] Property exists: {property_name}")
        return
    if get_res.status_code != 404:
        _raise_for_status(get_res, action=f"Check property {property_name}")

    create_payload = {
        "name": property_name,
        "label": property_label,
        "groupName": "contactinformation",
        "type": "datetime",
        "fieldType": "date",
        "description": "Appointment date used by VoxBulk Appointment Manager",
    }
    create_res = client.post(PROPERTIES_BASE, headers=_headers(token), json=create_payload)
    _raise_for_status(create_res, action=f"Create property {property_name}")
    print(f"[ok] Created property: {property_name}")


def _list_name_match(row: dict[str, Any], expected: str) -> bool:
    return str(row.get("name") or "").strip().lower() == expected.strip().lower()


def _find_or_create_list(client: httpx.Client, token: str, list_name: str) -> str:
    search_payload = {
        "count": 100,
        "processingTypes": ["MANUAL", "SNAPSHOT"],
        "objectTypeId": "0-1",
        "query": list_name,
    }
    search_res = client.post(LISTS_SEARCH, headers=_headers(token), json=search_payload)
    _raise_for_status(search_res, action="Search lists")
    lists = (search_res.json() or {}).get("lists") or []
    for row in lists:
        if isinstance(row, dict) and _list_name_match(row, list_name):
            list_id = str(row.get("listId") or row.get("ilsListId") or "").strip()
            if list_id:
                print(f"[ok] Using existing list: {list_name} ({list_id})")
                return list_id

    create_res = client.post(
        LISTS_BASE,
        headers=_headers(token),
        json={"name": list_name, "objectTypeId": "0-1", "processingType": "MANUAL"},
    )
    _raise_for_status(create_res, action=f"Create list {list_name}")
    list_id = str((create_res.json() or {}).get("list", {}).get("listId") or "").strip()
    if not list_id:
        raise HubspotSeedError("Create list succeeded but no listId returned")
    print(f"[ok] Created list: {list_name} ({list_id})")
    return list_id


def _lookup_contact_id(client: httpx.Client, token: str, email: str) -> str | None:
    payload = {
        "filterGroups": [
            {"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]},
        ],
        "properties": ["email"],
        "limit": 1,
    }
    res = client.post(CONTACTS_SEARCH, headers=_headers(token), json=payload)
    _raise_for_status(res, action=f"Search contact by email {email}")
    rows = (res.json() or {}).get("results") or []
    if not rows:
        return None
    first = rows[0] if isinstance(rows[0], dict) else {}
    cid = str(first.get("id") or "").strip()
    return cid or None


def _upsert_contacts(client: httpx.Client, token: str, rows: list[ContactSeedRow], date_property: str) -> list[str]:
    payload = {
        "idProperty": "email",
        "inputs": [
            {
                "id": row.email,
                "properties": {
                    "firstname": row.first_name,
                    "lastname": row.last_name,
                    "email": row.email,
                    "phone": row.phone,
                    date_property: row.appointment_iso,
                    "company": "VoxBulk Test",
                    "jobtitle": row.service_type,
                    "city": row.branch,
                },
            }
            for row in rows
        ],
    }
    res = client.post(CONTACTS_BATCH_UPSERT, headers=_headers(token), json=payload)
    _raise_for_status(res, action="Batch upsert contacts")
    body = res.json() or {}
    results = body.get("results") or []
    ids: list[str] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("id") or "").strip()
        if cid:
            ids.append(cid)

    # Fallback lookup by email if HubSpot omitted IDs in response.
    if len(ids) < len(rows):
        found = set(ids)
        for row in rows:
            cid = _lookup_contact_id(client, token, row.email)
            if cid and cid not in found:
                ids.append(cid)
                found.add(cid)
    if not ids:
        raise HubspotSeedError("Contacts upserted but no contact IDs were resolved")
    print(f"[ok] Upserted contacts: {len(rows)} (resolved IDs: {len(ids)})")
    return ids


def _add_contacts_to_list(client: httpx.Client, token: str, list_id: str, contact_ids: list[str]) -> None:
    if not contact_ids:
        return
    chunk_size = 100
    total = 0
    for i in range(0, len(contact_ids), chunk_size):
        chunk = contact_ids[i : i + chunk_size]
        res = client.put(
            f"{LISTS_BASE}/{list_id}/memberships/add",
            headers=_headers(token),
            json=chunk,
        )
        _raise_for_status(res, action=f"Add contacts to list {list_id}")
        total += len(chunk)
    print(f"[ok] Added contacts to list: {total}")


def _phone_for(index: int) -> str:
    # UK-like deterministic test range
    return f"+4477009{10000 + index:05d}"[:13]


def _plus_email(base_email: str, tag: str) -> str:
    base = base_email.strip().lower()
    if "@" not in base:
        raise HubspotSeedError(f"Invalid base email: {base_email}")
    local, domain = base.split("@", 1)
    local = local.split("+", 1)[0]
    return f"{local}+{tag}@{domain}"


def _random_email(index: int) -> str:
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"voxbulk.appt.test{index}.{rand}@example.com"


def _build_rows(
    *,
    count: int,
    base_email: str | None,
    start_days_ahead: int,
) -> list[ContactSeedRow]:
    names = [
        ("Sara", "Patel"),
        ("Jamal", "Okafor"),
        ("Amelia", "Chen"),
        ("Omar", "Hassan"),
        ("Alex", "Turner"),
        ("Priya", "Shah"),
        ("Maja", "Larsen"),
        ("Luca", "Bianchi"),
        ("Hannah", "Wright"),
        ("David", "Schmidt"),
    ]
    services = ["Hygiene visit", "Implant follow-up", "Check-up", "Consultation"]
    branches = ["London", "Manchester", "Birmingham", "Leeds"]
    now = datetime.now(timezone.utc)
    rows: list[ContactSeedRow] = []
    for i in range(count):
        first, last = names[i % len(names)]
        day = start_days_ahead + i
        hour = 9 + (i % 6)
        minute = 0 if i % 2 == 0 else 30
        appt = (now + timedelta(days=day)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        email = _plus_email(base_email, f"appt{i+1}") if base_email else _random_email(i + 1)
        rows.append(
            ContactSeedRow(
                email=email,
                first_name=first,
                last_name=last,
                phone=_phone_for(i + 1),
                appointment_iso=appt.isoformat().replace("+00:00", "Z"),
                service_type=services[i % len(services)],
                branch=branches[i % len(branches)],
            )
        )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed HubSpot appointment test data for VoxBulk")
    parser.add_argument("--token", default=os.getenv("HUBSPOT_ACCESS_TOKEN", "").strip(), help="HubSpot private app token")
    parser.add_argument("--count", type=int, default=8, help="Number of contacts to seed (default: 8)")
    parser.add_argument("--base-email", default="", help="Optional base inbox for plus-addressing (e.g. you@gmail.com)")
    parser.add_argument("--list-name", default="VoxBulk · Appointment test", help="Static HubSpot list name")
    parser.add_argument("--date-property", default="appointment_date", help="HubSpot datetime property for appointments")
    parser.add_argument("--date-label", default="Appointment Date", help="Label when creating the date property")
    parser.add_argument("--start-days-ahead", type=int, default=1, help="First appointment offset from today (days)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    token = str(args.token or "").strip()
    if not token:
        raise SystemExit("Missing HubSpot token. Use --token or HUBSPOT_ACCESS_TOKEN.")
    count = max(1, min(int(args.count), 200))
    date_property = _safe_slug(str(args.date_property or "appointment_date"))
    base_email = str(args.base_email or "").strip() or None

    rows = _build_rows(count=count, base_email=base_email, start_days_ahead=max(0, int(args.start_days_ahead)))
    with httpx.Client(timeout=60.0) as client:
        _ensure_property(client, token, property_name=date_property, property_label=str(args.date_label or "Appointment Date"))
        list_id = _find_or_create_list(client, token, str(args.list_name or "VoxBulk · Appointment test"))
        contact_ids = _upsert_contacts(client, token, rows, date_property)
        _add_contacts_to_list(client, token, list_id, contact_ids)

    print("")
    print("Seed complete ✅")
    print(f"List: {args.list_name} ({list_id})")
    print(f"Date property: {date_property}")
    print(f"Contacts seeded: {len(rows)}")
    print("")
    print("Next in VoxBulk:")
    print("1) Settings → Integrations → HubSpot: Connect + Test connection")
    print("2) Appointments setup: set CRM date property and select this list")
    print("3) Click Sync CRM in Appointments")


if __name__ == "__main__":
    main()
