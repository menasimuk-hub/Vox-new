#!/usr/bin/env python3
"""Seed end-to-end test data for Appointment Manager + WA Survey.

What this script seeds:
1) Local org data (appointments module + survey module enabled)
2) Appointment WA template catalog (local rows if missing)
3) WA survey test template pack + a post-visit survey order
4) Appointment settings with all key options enabled
5) Local appointments across statuses and CRM object variants
6) Optional HubSpot test data for contacts + deals (when token is provided)

Usage:
  cd voxbulk-api
  python scripts/seed_appointment_wa_survey_test_data.py --email user@user.com

  HUBSPOT_ACCESS_TOKEN=... python scripts/seed_appointment_wa_survey_test_data.py \
    --email user@user.com --hubspot-date-property appointment_date --hubspot-count 8
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.models.appointment import Appointment, AppointmentLog
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.models.user import User
from app.services.appointment_settings_service import save_config
from app.services.appointment_whatsapp_template_service import AppointmentWhatsappTemplateService
from app.services.hubspot_connection_service import save_hubspot_config, update_hubspot_settings
from app.services.org_enabled_services import (
    merge_admin_allowed_services,
    parse_allowed_services,
    parse_enabled_services,
)
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService
from app.services.survey_wa_test_pack_seed_service import SurveyWaTestPackSeedService

HUBSPOT_API = "https://api.hubapi.com"
CONTACTS_BATCH_UPSERT = f"{HUBSPOT_API}/crm/v3/objects/contacts/batch/upsert"
DEALS_BATCH_CREATE = f"{HUBSPOT_API}/crm/v3/objects/deals/batch/create"
PROPERTIES_BASE = f"{HUBSPOT_API}/crm/v3/properties"
LISTS_SEARCH = f"{HUBSPOT_API}/crm/v3/lists/search"
LISTS_BASE = f"{HUBSPOT_API}/crm/v3/lists"


class SeedError(Exception):
    pass


@dataclass
class LocalSeedResult:
    org_id: str
    org_name: str
    order_id: str
    appointment_count: int
    wa_template_name: str


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _raise_for_status(res: httpx.Response, *, action: str) -> None:
    if res.status_code >= 400:
        raise SeedError(f"{action} failed ({res.status_code}): {res.text[:300]}")


def _safe_slug(raw: str) -> str:
    text = str(raw or "").strip().lower()
    out = []
    for ch in text:
        out.append(ch if ch.isalnum() else "_")
    slug = "".join(out).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug[:50] or "appointment_date"


def _enable_services(org: Organisation) -> None:
    allowed = parse_allowed_services(org.allowed_services_json)
    enabled = parse_enabled_services(org.enabled_services_json)
    wanted = {
        "appointments": True,
        "survey": True,
        "interview": True,
    }
    merged_allowed, merged_enabled = merge_admin_allowed_services(allowed, enabled, wanted)
    org.allowed_services_json = json.dumps(merged_allowed, ensure_ascii=False)
    org.enabled_services_json = json.dumps(merged_enabled, ensure_ascii=False)


def _resolve_org_context(db, email: str) -> tuple[Organisation, User]:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        raise SeedError(f"User not found: {email}")
    membership = db.execute(
        select(OrganisationMembership).where(OrganisationMembership.user_id == user.id).limit(1)
    ).scalar_one_or_none()
    if membership is None:
        raise SeedError(f"No organisation membership for {email}")
    org = db.get(Organisation, membership.org_id)
    if org is None:
        raise SeedError("Organisation not found for membership")
    return org, user


def _find_or_create_post_survey_order(db, *, org: Organisation, user: User, survey_type_id: str | None) -> ServiceOrder:
    existing = db.execute(
        select(ServiceOrder).where(
            ServiceOrder.org_id == org.id,
            ServiceOrder.service_code == "survey",
            ServiceOrder.title == "Post-visit WA survey (test)",
        )
    ).scalar_one_or_none()
    now = datetime.utcnow()
    config = {
        "survey_name": "Post-visit WA survey (test)",
        "survey_channel": "whatsapp",
        "channels": ["whatsapp"],
        "contact_method": "whatsapp",
        "goal": "Post-visit appointment feedback",
        "organisation_name": org.name or "VoxBulk Org",
        "survey_organiser_name": "VoxBulk",
        "whatsapp_flow": {
            "intro": "Hi {{1}}, thanks for visiting us. Can you answer 3 quick questions?",
            "questions": [
                {
                    "id": "q1_rate",
                    "order": 1,
                    "text": "How was your overall experience?",
                    "answer_type": "choice",
                    "options": ["Bad", "Good", "Excellent"],
                },
                {
                    "id": "q2_recommend",
                    "order": 2,
                    "text": "Would you recommend us to a friend?",
                    "answer_type": "choice",
                    "options": ["Yes", "No"],
                },
                {
                    "id": "q3_feedback",
                    "order": 3,
                    "text": "Anything we should improve?",
                    "answer_type": "open",
                },
            ],
        },
    }
    if survey_type_id:
        config["survey_type_id"] = survey_type_id

    if existing is None:
        order = ServiceOrderService.create_order(
            db,
            org_id=org.id,
            user_id=user.id,
            service_code="survey",
            title="Post-visit WA survey (test)",
            config=config,
        )
    else:
        order = existing
        try:
            merged = json.loads(order.config_json or "{}")
            if not isinstance(merged, dict):
                merged = {}
        except Exception:
            merged = {}
        merged.update(config)
        order.config_json = json.dumps(merged, ensure_ascii=False)
        order.status = "running"
        order.started_at = order.started_at or now
        order.updated_at = now
        db.add(order)
        db.commit()
        db.refresh(order)
    if order.status in {"draft", "approved"}:
        order.status = "running"
        order.started_at = order.started_at or now
        order.updated_at = now
        db.add(order)
        db.commit()
        db.refresh(order)
    return order


def _seed_local_appointments(db, *, org: Organisation, wa_template_name: str, post_survey_order_id: str) -> int:
    now = datetime.utcnow()
    marker = "seed:appointment_wa_survey_e2e_v1"

    old_rows = db.execute(
        select(Appointment).where(
            Appointment.org_id == org.id,
            Appointment.notes == marker,
        )
    ).scalars().all()
    for row in old_rows:
        db.execute(AppointmentLog.__table__.delete().where(AppointmentLog.appointment_id == row.id))
        db.delete(row)
    db.commit()

    rows = [
        {
            "contact_name": "Sara Patel",
            "contact_phone": "+447700900101",
            "contact_email": "sara.patel@example.com",
            "status": "scheduled",
            "crm_record_id": "contacts:seed-contact-001",
            "days": 2,
            "service_type": "Hygiene visit",
            "branch": "London",
        },
        {
            "contact_name": "Jamal Okafor",
            "contact_phone": "+447700900102",
            "contact_email": "jamal.okafor@example.com",
            "status": "confirmed",
            "crm_record_id": "contacts:seed-contact-002",
            "days": 1,
            "service_type": "Implant consultation",
            "branch": "Manchester",
        },
        {
            "contact_name": "Amelia Chen",
            "contact_phone": "+447700900103",
            "contact_email": "amelia.chen@example.com",
            "status": "rescheduled",
            "crm_record_id": "deals:seed-deal-001",
            "days": 3,
            "service_type": "Whitening consult",
            "branch": "Birmingham",
            "rescheduled_offset_hours": 30,
        },
        {
            "contact_name": "Omar Hassan",
            "contact_phone": "+447700900104",
            "contact_email": "omar.hassan@example.com",
            "status": "cancelled",
            "crm_record_id": "deals:seed-deal-002",
            "days": 4,
            "service_type": "Check-up",
            "branch": "Leeds",
        },
        {
            "contact_name": "Priya Shah",
            "contact_phone": "+447700900105",
            "contact_email": "priya.shah@example.com",
            "status": "no_show",
            "crm_record_id": "2-1234567:seed-custom-001",
            "days": 1,
            "service_type": "Follow-up",
            "branch": "London",
        },
        {
            "contact_name": "David Schmidt",
            "contact_phone": "+447700900106",
            "contact_email": "david.schmidt@example.com",
            "status": "confirmed",
            "crm_record_id": "deals:seed-deal-003",
            "days": -1,
            "service_type": "Root canal",
            "branch": "Manchester",
        },
    ]

    created = 0
    for idx, row in enumerate(rows, start=1):
        appt_dt = now + timedelta(days=int(row["days"]), hours=10 + (idx % 4))
        appt_id = str(uuid.uuid4())
        status = str(row["status"])
        wa_sent = status in {"confirmed", "rescheduled", "cancelled"} or row["days"] <= 1
        appt = Appointment(
            id=appt_id,
            org_id=org.id,
            contact_name=str(row["contact_name"]),
            contact_phone=str(row["contact_phone"]),
            contact_email=str(row["contact_email"]),
            appointment_datetime=appt_dt,
            timezone="Europe/London",
            branch=str(row["branch"]),
            service_type=str(row["service_type"]),
            status=status,
            crm_source="hubspot",
            crm_record_id=str(row["crm_record_id"]),
            wa_confirmation_sent_at=(appt_dt - timedelta(hours=48)) if wa_sent else None,
            wa_confirmation_status="delivered" if wa_sent else None,
            call_triggered_at=(appt_dt - timedelta(hours=24)) if status in {"confirmed", "rescheduled", "no_show"} else None,
            call_outcome="confirmed" if status == "confirmed" else ("rescheduled" if status == "rescheduled" else None),
            confirmation_channel="whatsapp" if status == "confirmed" else ("call" if status == "rescheduled" else None),
            confirmed_at=(appt_dt - timedelta(hours=30)) if status == "confirmed" else None,
            rescheduled_to_datetime=(
                appt_dt + timedelta(hours=int(row.get("rescheduled_offset_hours") or 0))
                if status == "rescheduled"
                else None
            ),
            notes=marker,
            post_survey_sent_at=None,
            created_at=now,
            updated_at=now,
        )
        db.add(appt)
        db.flush()
        db.add(
            AppointmentLog(
                id=str(uuid.uuid4()),
                appointment_id=appt.id,
                event_type="seeded",
                detail_json=json.dumps(
                    {
                        "seed_marker": marker,
                        "wa_template_name": wa_template_name,
                        "post_survey_order_id": post_survey_order_id,
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        created += 1

    db.commit()
    return created


def _ensure_hubspot_property(
    client: httpx.Client,
    token: str,
    *,
    object_type_id: str,
    property_name: str,
    property_label: str,
    property_type: str,
    field_type: str,
) -> None:
    get_res = client.get(
        f"{PROPERTIES_BASE}/{object_type_id}/{property_name}",
        headers=_headers(token),
    )
    if get_res.status_code == 200:
        return
    if get_res.status_code != 404:
        _raise_for_status(get_res, action=f"check property {object_type_id}.{property_name}")

    payload = {
        "name": property_name,
        "label": property_label,
        "type": property_type,
        "fieldType": field_type,
        "groupName": "contactinformation" if object_type_id == "0-1" else "dealinformation",
    }
    create_res = client.post(f"{PROPERTIES_BASE}/{object_type_id}", headers=_headers(token), json=payload)
    _raise_for_status(create_res, action=f"create property {object_type_id}.{property_name}")


def _find_or_create_hubspot_list(client: httpx.Client, token: str, list_name: str) -> str:
    search_res = client.post(
        LISTS_SEARCH,
        headers=_headers(token),
        json={
            "count": 100,
            "processingTypes": ["MANUAL", "SNAPSHOT"],
            "objectTypeId": "0-1",
            "query": list_name,
        },
    )
    _raise_for_status(search_res, action="search lists")
    rows = (search_res.json() or {}).get("lists") or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("name") or "").strip().lower() == list_name.strip().lower():
            list_id = str(row.get("listId") or row.get("ilsListId") or "").strip()
            if list_id:
                return list_id
    create_res = client.post(
        LISTS_BASE,
        headers=_headers(token),
        json={"name": list_name, "objectTypeId": "0-1", "processingType": "MANUAL"},
    )
    _raise_for_status(create_res, action=f"create list {list_name}")
    list_id = str((create_res.json() or {}).get("list", {}).get("listId") or "").strip()
    if not list_id:
        raise SeedError("HubSpot list creation returned no listId")
    return list_id


def _upsert_hubspot_contacts(
    client: httpx.Client,
    token: str,
    *,
    count: int,
    date_property: str,
    base_email: str,
) -> list[str]:
    now = datetime.now(timezone.utc)
    rows = []
    for idx in range(count):
        tag = f"voxbulk.appt.{now.strftime('%Y%m%d')}.{idx+1}"
        local, domain = base_email.split("@", 1)
        local = local.split("+", 1)[0]
        email = f"{local}+{tag}@{domain}"
        appt_time = (now + timedelta(days=idx + 1, hours=10 + (idx % 3))).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        rows.append(
            {
                "id": email,
                "properties": {
                    "firstname": f"Contact{idx+1}",
                    "lastname": "Seed",
                    "email": email,
                    "phone": f"+4477009{10000 + idx:05d}"[:13],
                    date_property: appt_time,
                    "voxbulk_appointment_status": "scheduled",
                },
            }
        )
    upsert_res = client.post(
        CONTACTS_BATCH_UPSERT,
        headers=_headers(token),
        json={"idProperty": "email", "inputs": rows},
    )
    _raise_for_status(upsert_res, action="upsert contacts")
    results = (upsert_res.json() or {}).get("results") or []
    ids: list[str] = []
    for row in results:
        if isinstance(row, dict):
            rid = str(row.get("id") or "").strip()
            if rid:
                ids.append(rid)
    return ids


def _add_contacts_to_list(client: httpx.Client, token: str, list_id: str, contact_ids: list[str]) -> None:
    if not contact_ids:
        return
    for i in range(0, len(contact_ids), 100):
        chunk = contact_ids[i : i + 100]
        res = client.put(
            f"{LISTS_BASE}/{list_id}/memberships/add",
            headers=_headers(token),
            json=chunk,
        )
        _raise_for_status(res, action=f"add contacts to list {list_id}")


def _create_hubspot_deals(
    client: httpx.Client,
    token: str,
    *,
    count: int,
    date_property: str,
) -> list[str]:
    now = datetime.now(timezone.utc)
    inputs = []
    for idx in range(count):
        deal_name = f"VoxBulk Deal Seed {now.strftime('%Y%m%d%H%M')}-{idx+1}-{uuid.uuid4().hex[:6]}"
        appt_time = (now + timedelta(days=idx + 1, hours=12 + (idx % 2))).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        inputs.append(
            {
                "properties": {
                    "dealname": deal_name,
                    "pipeline": "default",
                    "dealstage": "appointmentscheduled",
                    "contact_phone": f"+4477019{20000 + idx:05d}"[:13],
                    date_property: appt_time,
                    "voxbulk_appointment_status": "scheduled",
                }
            }
        )
    res = client.post(DEALS_BATCH_CREATE, headers=_headers(token), json={"inputs": inputs})
    _raise_for_status(res, action="create deals")
    ids: list[str] = []
    for row in (res.json() or {}).get("results") or []:
        if isinstance(row, dict):
            rid = str(row.get("id") or "").strip()
            if rid:
                ids.append(rid)
    return ids


def _seed_hubspot_data(
    db,
    *,
    org: Organisation,
    token: str,
    list_name: str,
    date_property: str,
    count: int,
) -> dict[str, Any]:
    date_property = _safe_slug(date_property)
    with httpx.Client(timeout=60.0) as client:
        _ensure_hubspot_property(
            client,
            token,
            object_type_id="0-1",
            property_name=date_property,
            property_label="Appointment date",
            property_type="datetime",
            field_type="date",
        )
        _ensure_hubspot_property(
            client,
            token,
            object_type_id="0-1",
            property_name="voxbulk_appointment_status",
            property_label="VoxBulk appointment status",
            property_type="string",
            field_type="text",
        )
        _ensure_hubspot_property(
            client,
            token,
            object_type_id="0-3",
            property_name=date_property,
            property_label="Appointment date",
            property_type="datetime",
            field_type="date",
        )
        _ensure_hubspot_property(
            client,
            token,
            object_type_id="0-3",
            property_name="contact_phone",
            property_label="Contact phone",
            property_type="string",
            field_type="text",
        )
        _ensure_hubspot_property(
            client,
            token,
            object_type_id="0-3",
            property_name="voxbulk_appointment_status",
            property_label="VoxBulk appointment status",
            property_type="string",
            field_type="text",
        )

        list_id = _find_or_create_hubspot_list(client, token, list_name)
        contacts = _upsert_hubspot_contacts(
            client,
            token,
            count=max(1, count),
            date_property=date_property,
            base_email="voxbulk.seed@example.com",
        )
        _add_contacts_to_list(client, token, list_id, contacts)
        deals = _create_hubspot_deals(
            client,
            token,
            count=max(1, count),
            date_property=date_property,
        )

    save_hubspot_config(
        db,
        org.id,
        {
            "access_token": token,
            "hub_id": "seeded",
        },
    )
    update_hubspot_settings(
        db,
        org.id,
        appointment_list_id=list_id,
        appointment_confirmed_list_id="",
        appointment_cancelled_list_id="",
    )
    return {
        "date_property": date_property,
        "appointment_list_id": list_id,
        "contacts_seeded": len(contacts),
        "deals_seeded": len(deals),
    }


def seed_all(
    *,
    email: str,
    hubspot_token: str | None,
    hubspot_list_name: str,
    hubspot_date_property: str,
    hubspot_count: int,
) -> dict[str, Any]:
    Session = get_sessionmaker()
    with Session() as db:
        PlatformCatalogService.ensure_defaults(db)
        org, user = _resolve_org_context(db, email=email)
        _enable_services(org)
        db.add(org)
        db.commit()
        db.refresh(org)

        AppointmentWhatsappTemplateService.ensure_catalog_seeded(db)
        customer_templates = AppointmentWhatsappTemplateService.list_customer_templates(db)
        if not customer_templates:
            raise SeedError("Appointment WA template catalog is empty after seeding")
        wa_template_name = str(customer_templates[0].get("name") or "appt_confirm_v1")

        survey_pack = SurveyWaTestPackSeedService.ensure_test_pack(db)
        survey_type_id = str((survey_pack.get("survey_type") or {}).get("id") or "").strip() or None
        post_survey_order = _find_or_create_post_survey_order(
            db,
            org=org,
            user=user,
            survey_type_id=survey_type_id,
        )

        save_config(
            db,
            org.id,
            {
                "setup_complete": True,
                "workspace_name": "Appointment + WA survey test workspace",
                "crm_provider": "hubspot",
                "crm_object": "contacts",
                "crm_date_property": _safe_slug(hubspot_date_property),
                "sync_interval_minutes": 30,
                "wa_template_name": wa_template_name,
                "wa_send_hours_before": 72,
                "call_hours_before": 24,
                "wa_enabled": True,
                "call_enabled": True,
                "reminder_sequence_json": [
                    {"hours_before": 72, "channel": "whatsapp", "template_name": wa_template_name},
                    {"hours_before": 24, "channel": "call"},
                ],
                "calendar_enabled": False,
                "post_survey_enabled": True,
                "post_survey_order_id": post_survey_order.id,
                "post_survey_delay_hours": 1,
                "outreach_window_start": "09:00",
                "outreach_window_end": "18:00",
            },
        )
        local_count = _seed_local_appointments(
            db,
            org=org,
            wa_template_name=wa_template_name,
            post_survey_order_id=post_survey_order.id,
        )
        local = LocalSeedResult(
            org_id=str(org.id),
            org_name=str(org.name or ""),
            order_id=str(post_survey_order.id),
            appointment_count=local_count,
            wa_template_name=wa_template_name,
        )

        output: dict[str, Any] = {
            "ok": True,
            "org_id": local.org_id,
            "org_name": local.org_name,
            "post_survey_order_id": local.order_id,
            "local_appointments_seeded": local.appointment_count,
            "appointment_wa_template": local.wa_template_name,
            "survey_pack": {
                "industry": (survey_pack.get("industry") or {}).get("slug"),
                "survey_type": (survey_pack.get("survey_type") or {}).get("slug"),
                "templates": int(survey_pack.get("template_count") or 0),
            },
        }
        if hubspot_token:
            output["hubspot"] = _seed_hubspot_data(
                db,
                org=org,
                token=hubspot_token,
                list_name=hubspot_list_name,
                date_property=hubspot_date_property,
                count=max(1, hubspot_count),
            )
        return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Appointment + WA survey test data")
    parser.add_argument("--email", default="user@user.com", help="Existing VoxBulk user email")
    parser.add_argument("--hubspot-token", default=None, help="Optional HubSpot access token")
    parser.add_argument("--hubspot-list-name", default="VoxBulk · Appointment test", help="HubSpot static list name")
    parser.add_argument("--hubspot-date-property", default="appointment_date", help="HubSpot datetime property name")
    parser.add_argument("--hubspot-count", type=int, default=6, help="How many contacts/deals to seed")
    args = parser.parse_args()

    token = (args.hubspot_token or os.getenv("HUBSPOT_ACCESS_TOKEN") or "").strip() or None
    result = seed_all(
        email=str(args.email).strip().lower(),
        hubspot_token=token,
        hubspot_list_name=str(args.hubspot_list_name),
        hubspot_date_property=str(args.hubspot_date_property),
        hubspot_count=max(1, int(args.hubspot_count)),
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
