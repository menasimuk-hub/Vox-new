#!/usr/bin/env python3
"""Seed demo CRM appointments for local dashboard testing.

Usage:
  cd voxbulk-api && python scripts/seed_demo_appointments.py
  cd voxbulk-api && python scripts/seed_demo_appointments.py --email user@user.com
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.appointment import Appointment, AppointmentLog
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.org_enabled_services import merge_admin_allowed_services, parse_allowed_services, parse_enabled_services
from app.services.platform_catalog_service import PlatformCatalogService


DEMO_ROWS = [
    ("Sara Patel", "+447700900123", "hubspot", "confirmed", "Hygiene visit", "London — Marylebone", 2),
    ("David Schmidt", "+4915123456789", "pipedrive", "scheduled", "Whitening consult", "Berlin — Mitte", 3),
    ("Maja Larsen", "+4531415926", "zoho", "rescheduled", "Implant review", "Copenhagen — Central", 4),
    ("Yusuf Adeyemi", "+447700900889", "hubspot", "cancelled", "Filling", "London — Marylebone", 5),
    ("Elena Rossi", "+393401234567", "manual", "scheduled", "Hygiene visit", "Milan — Brera", 6),
    ("Jamal Okafor", "+447700900445", "hubspot", "confirmed", "Implant follow-up", "Manchester — Deansgate", 7),
    ("Priya Shah", "+447700900221", "pipedrive", "scheduled", "Whitening", "London — Canary Wharf", 8),
    ("Tom Becker", "+14155550177", "zoho", "no_show", "Consultation", "London — Marylebone", 1),
    ("Amelia Chen", "+447700900332", "hubspot", "confirmed", "Check-up", "Manchester — Deansgate", 9),
    ("Luca Bianchi", "+39335111222", "manual", "scheduled", "Consultation", "Milan — Brera", 10),
    ("Hannah Wright", "+447700900778", "pipedrive", "confirmed", "Hygiene visit", "London — Canary Wharf", 11),
    ("Omar Hassan", "+447700900991", "hubspot", "scheduled", "Root canal", "London — Marylebone", 12),
]


def _enable_services(org: Organisation) -> None:
    allowed = parse_allowed_services(org.allowed_services_json)
    enabled = parse_enabled_services(org.enabled_services_json)
    new_allowed, new_enabled = merge_admin_allowed_services(allowed, enabled, {"appointments": True})
    org.allowed_services_json = json.dumps(new_allowed)
    org.enabled_services_json = json.dumps(new_enabled)


def _config() -> dict:
    return {
        "setup_complete": True,
        "workspace_name": "Demo Appointment Manager",
        "crm_provider": "hubspot",
        "crm_object": "contacts",
        "crm_date_property": "appointment_date",
        "sync_interval_minutes": 60,
        "outreach_window_start": "09:00",
        "outreach_window_end": "16:00",
        "wa_template_name": "appt_confirm_v1",
        "wa_send_hours_before": 72,
        "call_hours_before": 24,
        "wa_enabled": True,
        "call_enabled": True,
        "reminder_sequence_json": [
            {"id": "s1", "when": "72h before", "enabled": True, "message": "Hi {first_name}, reminder 72h before."},
            {"id": "s2", "when": "24h before", "enabled": True, "message": "Hi {first_name}, reminder 24h before."},
        ],
    }


def seed(*, email: str) -> None:
    Session = get_sessionmaker()
    with Session() as db:
        PlatformCatalogService.ensure_defaults(db)
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            raise SystemExit(f"User not found: {email}")
        membership = db.execute(
            select(OrganisationMembership).where(OrganisationMembership.user_id == user.id).limit(1)
        ).scalar_one_or_none()
        if membership is None:
            raise SystemExit(f"No organisation for {email}")
        org = db.get(Organisation, membership.org_id)
        if org is None:
            raise SystemExit("Organisation missing")

        _enable_services(org)
        org.appointment_manager_config_json = json.dumps(_config(), ensure_ascii=False)

        existing = db.execute(select(Appointment).where(Appointment.org_id == org.id)).scalars().all()
        for row in existing:
            db.execute(AppointmentLog.__table__.delete().where(AppointmentLog.appointment_id == row.id))
            db.delete(row)

        now = datetime.utcnow()
        for name, phone, crm, status, service, branch, day_offset in DEMO_ROWS:
            appt_id = str(uuid.uuid4())
            appt_dt = now + timedelta(days=day_offset, hours=9 + (day_offset % 5))
            wa_sent = status != "scheduled" or crm != "manual"
            appt = Appointment(
                id=appt_id,
                org_id=org.id,
                contact_name=name,
                contact_phone=phone,
                appointment_datetime=appt_dt,
                timezone="Europe/London",
                branch=branch,
                service_type=service,
                status=status,
                crm_source=crm,
                crm_record_id=f"crm-{appt_id[:8]}",
                wa_confirmation_sent_at=appt_dt - timedelta(hours=48) if wa_sent else None,
                wa_confirmation_status="delivered" if wa_sent else None,
                call_triggered_at=appt_dt - timedelta(hours=24) if status in {"confirmed", "rescheduled", "no_show"} else None,
                call_outcome="confirmed" if status == "confirmed" else ("rescheduled" if status == "rescheduled" else None),
                confirmation_channel="whatsapp" if status == "confirmed" and wa_sent else ("call" if status == "confirmed" else None),
                confirmed_at=appt_dt - timedelta(hours=40) if status == "confirmed" else None,
            )
            db.add(appt)
            db.add(
                AppointmentLog(
                    id=str(uuid.uuid4()),
                    appointment_id=appt_id,
                    event_type="created",
                    detail_json=json.dumps({"source": crm}),
                )
            )
            if wa_sent:
                db.add(
                    AppointmentLog(
                        id=str(uuid.uuid4()),
                        appointment_id=appt_id,
                        event_type="wa_sent",
                        detail_json=json.dumps({"template": "appt_confirm_v1"}),
                    )
                )
            if status == "confirmed":
                db.add(
                    AppointmentLog(
                        id=str(uuid.uuid4()),
                        appointment_id=appt_id,
                        event_type="confirmed",
                        detail_json=json.dumps({"channel": appt.confirmation_channel}),
                    )
                )

        db.add(org)
        db.commit()
        print(f"Seeded {len(DEMO_ROWS)} appointments for org {org.name} ({email})")
        print("Enabled appointments module. Open /appointments in dashboard.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default="user@user.com")
    args = parser.parse_args()
    seed(email=args.email.strip().lower())


if __name__ == "__main__":
    main()
