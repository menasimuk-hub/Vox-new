#!/usr/bin/env python3
"""Seed care & repair demo surveys (WA + AI call) for HubSpot result sync testing.

Creates 4 completed respondents (2 WhatsApp, 2 AI call) on the target user's org.
Use Gmail plus-addressing by default so contacts are distinct but land in one inbox.

Usage:
  cd voxbulk-api
  source .venv/bin/activate
  python scripts/seed_demo_survey_hubspot.py

  python scripts/seed_demo_survey_hubspot.py --email zaghlolno@gmail.com
  python scripts/seed_demo_survey_hubspot.py --clear
  python scripts/seed_demo_survey_hubspot.py --seed-hubspot-pool
  python scripts/seed_demo_survey_hubspot.py --push-hubspot
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

try:
    from sqlalchemy import delete, select
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Run inside voxbulk-api/.venv:\n"
        "  source .venv/bin/activate && python scripts/seed_demo_survey_hubspot.py"
    ) from exc

from app.core.database import get_sessionmaker
from app.models.hubspot_contact import HubspotContact
from app.models.membership import OrganisationMembership
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.services.hubspot_connection_service import hubspot_status
from app.services.hubspot_contact_sync_service import sync_survey_result_to_hubspot
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService
from app.services.survey_analysis_service import ANALYSIS_VERSION, refresh_order_survey_report

DEMO_PACK_ID = "hubspot_sync_care_repair_v1"
DEFAULT_OWNER_EMAIL = "zaghlolno@gmail.com"

CARE_REPAIR_CONTACTS = [
    {
        "name": "Alex Turner",
        "email": "zaghlolno+care1@gmail.com",
        "phone": "+447700900501",
        "channel": "wa",
        "sentiment": "positive",
        "recommend_score": 9,
        "summary": "Repair completed on time; technician explained the work clearly.",
    },
    {
        "name": "Sam Patel",
        "email": "zaghlolno+care2@gmail.com",
        "phone": "+447700900502",
        "channel": "wa",
        "sentiment": "negative",
        "recommend_score": 4,
        "summary": "Waited three days for a callback about the boiler repair quote.",
    },
    {
        "name": "Jordan Lee",
        "email": "zaghlolno+care3@gmail.com",
        "phone": "+447700900503",
        "channel": "ai_call",
        "sentiment": "neutral",
        "recommend_score": 7,
        "summary": "Care repair visit was fine but scheduling felt rushed.",
    },
    {
        "name": "Riley Morgan",
        "email": "zaghlolno+care4@gmail.com",
        "phone": "+447700900504",
        "channel": "ai_call",
        "sentiment": "positive",
        "recommend_score": 10,
        "summary": "Emergency repair team arrived within two hours — excellent service.",
    },
]

WA_QUESTIONS = [
    "Was your care & repair booking easy to arrange?",
    "How would you rate the repair quality?",
    "Was the issue fully resolved?",
    "Anything else we should know?",
]

CALL_QUESTIONS = [
    "Did we reach you at a convenient time?",
    "How satisfied are you with the repair outcome?",
    "Would you use our care & repair service again?",
    "Please share any feedback about your experience.",
]


def _wa_config() -> dict:
    return {
        "demo_survey_pack": DEMO_PACK_ID,
        "survey_channel": "whatsapp",
        "delivery": "whatsapp",
        "channels": ["whatsapp"],
        "contact_method": "WhatsApp",
        "goal": "Care & repair customer feedback",
        "organisation_name": "Care & Repair Co",
        "survey_organiser_name": "Customer Care",
        "industry_slug": "automotive",
        "service_type": "Work quality",
        "script_approved": True,
        "allow_final_additional_feedback": True,
    }


def _call_config() -> dict:
    script = "\n".join(
        [
            "INTRO",
            "Hello, we are calling about your recent care and repair visit.",
            "",
            "QUESTIONS",
            *[f"{i + 1}. {q}" for i, q in enumerate(CALL_QUESTIONS)],
            "",
            "CLOSING",
            "Thank you for your feedback.",
        ]
    )
    return {
        "demo_survey_pack": DEMO_PACK_ID,
        "survey_channel": "ai_call",
        "channels": ["call"],
        "contact_method": "AI phone call",
        "goal": "Care & repair customer feedback",
        "organisation_name": "Care & Repair Co",
        "survey_organiser_name": "Customer Care",
        "industry_slug": "automotive",
        "service_type": "Work quality",
        "script_approved": True,
        "approved_script": script,
        "system_prompt": "Run a polite care and repair satisfaction survey.",
    }


def _wa_result(contact: dict, *, completed_at: datetime) -> dict:
    answers = [
        {"question": WA_QUESTIONS[0], "answer": "Yes", "answer_text": "Yes", "answer_source": "text"},
        {
            "question": WA_QUESTIONS[1],
            "answer": "Excellent" if contact["sentiment"] == "positive" else "Poor" if contact["sentiment"] == "negative" else "Good",
            "answer_text": "Excellent" if contact["sentiment"] == "positive" else "Poor" if contact["sentiment"] == "negative" else "Good",
            "answer_source": "text",
        },
        {
            "question": WA_QUESTIONS[2],
            "answer": "No" if contact["sentiment"] == "negative" else "Yes",
            "answer_text": "No" if contact["sentiment"] == "negative" else "Yes",
            "answer_source": "text",
        },
        {"question": WA_QUESTIONS[3], "answer": contact["summary"], "answer_text": contact["summary"], "answer_source": "text"},
    ]
    return {
        "channel": "whatsapp",
        "terminal_status": "completed",
        "completed_at": completed_at.isoformat(),
        "sentiment": contact["sentiment"],
        "recommend_score": contact["recommend_score"],
        "short_summary": contact["summary"],
        "analysis": {
            "sentiment": contact["sentiment"],
            "recommend_score": contact["recommend_score"],
            "short_summary": contact["summary"],
        },
        "wa_conversation": {
            "step": 4,
            "total": 4,
            "answers": answers,
            "completed_at": completed_at.isoformat(),
        },
        "final_additional_feedback": contact["summary"],
    }


def _call_result(contact: dict, *, completed_at: datetime) -> dict:
    extracted = [
        {"question": CALL_QUESTIONS[0], "answer": "Yes"},
        {
            "question": CALL_QUESTIONS[1],
            "answer": "Excellent" if contact["sentiment"] == "positive" else "Poor" if contact["sentiment"] == "negative" else "Good",
        },
        {"question": CALL_QUESTIONS[2], "answer": "Yes" if contact["recommend_score"] >= 7 else "No"},
        {"question": CALL_QUESTIONS[3], "answer": contact["summary"], "answer_text": contact["summary"]},
    ]
    return {
        "terminal_status": "completed",
        "completed_at": completed_at.isoformat(),
        "duration_seconds": 185,
        "transcript": f"Agent: Care and repair feedback survey.\nUser: {contact['summary']}",
        "analysis": {
            "short_summary": contact["summary"],
            "sentiment": contact["sentiment"],
            "recommend_score": contact["recommend_score"],
            "satisfaction_score": min(10, max(4, contact["recommend_score"])),
            "extracted_answers": extracted,
            "issues": ["follow-up"] if contact["sentiment"] == "negative" else [],
            "tags": ["care_repair"],
        },
        "analysis_saved_at": completed_at.isoformat(),
        "analysis_version": ANALYSIS_VERSION,
        "sentiment": contact["sentiment"],
        "recommend_score": contact["recommend_score"],
        "short_summary": contact["summary"],
    }


def _approve_payment_flow(db, order: ServiceOrder) -> ServiceOrder:
    if order.quote_total_pence <= 0 or order.status == "draft":
        order = ServiceOrderService.quote_order(db, order)
    if order.payment_status != "approved":
        if order.payment_status != "pending_approval":
            order = ServiceOrderService.submit_cash_payment(db, order, note="HubSpot demo seed")
        order = ServiceOrderService.admin_approve_payment(db, order, note="HubSpot demo seed — auto approved")
    return order


def _finish_order(db, order: ServiceOrder, *, channel: str) -> ServiceOrder:
    now = datetime.utcnow()
    order.payment_status = "approved"
    order.payment_method = order.payment_method or "cash"
    order.status = "completed"
    order.scheduled_start_at = order.scheduled_start_at or (now - timedelta(days=4))
    order.scheduled_end_at = order.scheduled_end_at or (now - timedelta(days=1))
    order.started_at = order.started_at or (now - timedelta(days=2))
    order.completed_at = now - timedelta(hours=3)
    order.updated_at = now
    recipients = ServiceOrderService.get_recipients(db, order.id)
    completed = sum(1 for r in recipients if str(r.status or "").lower() == "completed")
    order.report_json = json.dumps(
        {
            "demo": True,
            "demo_survey_pack": DEMO_PACK_ID,
            "channel": channel,
            "total": len(recipients),
            "completed": completed,
            "note": "Care & repair HubSpot sync demo",
        },
        ensure_ascii=False,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    if channel == "ai_call":
        refresh_order_survey_report(db, order)
    return order


def _clear_demo_orders(db, org_id: str) -> int:
    orders = list(
        db.execute(
            select(ServiceOrder).where(
                ServiceOrder.org_id == org_id,
                ServiceOrder.service_code == "survey",
            )
        ).scalars()
    )
    removed = 0
    for order in orders:
        try:
            cfg = json.loads(order.config_json or "{}")
        except Exception:
            continue
        if cfg.get("demo_survey_pack") != DEMO_PACK_ID:
            continue
        db.execute(delete(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id))
        db.delete(order)
        removed += 1
    if removed:
        db.commit()
    return removed


def _seed_hubspot_pool(db, org_id: str, contacts: list[dict]) -> int:
    now = datetime.utcnow()
    added = 0
    try:
        for idx, contact in enumerate(contacts, start=1):
            hs_id = f"demo-care-repair-{idx:03d}"
            existing = db.execute(
                select(HubspotContact).where(
                    HubspotContact.org_id == org_id,
                    HubspotContact.hubspot_contact_id == hs_id,
                )
            ).scalar_one_or_none()
            if existing:
                existing.name = contact["name"]
                existing.email = contact["email"]
                existing.phone = contact["phone"]
                existing.synced_at = now
                existing.updated_at = now
                db.add(existing)
                continue
            db.add(
                HubspotContact(
                    id=str(uuid.uuid4()),
                    org_id=org_id,
                    hubspot_contact_id=hs_id,
                    name=contact["name"],
                    email=contact["email"],
                    phone=contact["phone"],
                    raw_properties_json=json.dumps({"demo": True, "source": DEMO_PACK_ID}),
                    synced_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
            added += 1
        db.commit()
    except Exception as exc:
        db.rollback()
        print(f"HubSpot local pool skipped ({str(exc)[:120]}). Run migrations on VPS or omit --seed-hubspot-pool.")
        return 0
    return added


def _create_order(
    db,
    *,
    org_id: str,
    user_id: str,
    channel: str,
    title: str,
    contacts: list[dict],
) -> ServiceOrder:
    config = _wa_config() if channel == "wa" else _call_config()
    order = ServiceOrderService.create_order(
        db,
        org_id=org_id,
        user_id=user_id,
        service_code="survey",
        title=title,
        config=config,
    )
    rows = [{"name": c["name"], "phone": c["phone"], "email": c["email"]} for c in contacts]
    ServiceOrderService.replace_recipients(db, order, rows)
    db.refresh(order)

    order = _approve_payment_flow(db, order)
    now = datetime.utcnow()
    recipients = ServiceOrderService.get_recipients(db, order.id)
    for recipient, contact in zip(recipients, contacts, strict=True):
        completed_at = now - timedelta(hours=recipient.row_number)
        payload = _wa_result(contact, completed_at=completed_at) if channel == "wa" else _call_result(contact, completed_at=completed_at)
        recipient.status = "completed"
        recipient.result_json = json.dumps(payload, ensure_ascii=False)
        db.add(recipient)
    db.commit()
    return _finish_order(db, order, channel=channel)


def _push_results(db, org_id: str, orders: list[ServiceOrder]) -> None:
    status = hubspot_status(db, org_id)
    if not status.get("connected"):
        print("HubSpot not connected — skipped push. Connect in Settings → Integrations, then re-run with --push-hubspot.")
        return
    for order in orders:
        recipients = ServiceOrderService.get_recipients(db, order.id)
        for recipient in recipients:
            if str(recipient.status or "").lower() != "completed":
                continue
            try:
                result = sync_survey_result_to_hubspot(db, org_id, order=order, recipient=recipient, force=True)
                db.commit()
                label = recipient.name or recipient.email or recipient.id
                if result.get("skipped"):
                    print(f"  skip {label}: {result.get('reason') or 'unknown'}")
                else:
                    print(f"  pushed {label} → HubSpot contact {result.get('contact_id')}")
            except Exception as exc:
                print(f"  failed {recipient.name or recipient.id}: {str(exc)[:200]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed care & repair WA + AI call surveys for HubSpot sync testing")
    parser.add_argument("--email", default=DEFAULT_OWNER_EMAIL, help="Dashboard user email (org owner)")
    parser.add_argument("--clear", action="store_true", help="Remove prior demo orders from this pack")
    parser.add_argument(
        "--seed-hubspot-pool",
        action="store_true",
        help="Upsert local hubspot_contacts rows (helps phone matching; email still needs HubSpot CRM contact)",
    )
    parser.add_argument(
        "--push-hubspot",
        action="store_true",
        help="Attempt manual HubSpot push for each completed respondent after seeding",
    )
    args = parser.parse_args()

    wa_contacts = [c for c in CARE_REPAIR_CONTACTS if c["channel"] == "wa"]
    call_contacts = [c for c in CARE_REPAIR_CONTACTS if c["channel"] == "ai_call"]

    with get_sessionmaker()() as db:
        PlatformCatalogService.ensure_defaults(db)

        user = db.execute(select(User).where(User.email == args.email)).scalar_one_or_none()
        if user is None:
            raise SystemExit(f"User not found: {args.email} (start the API locally once to bootstrap dev users)")

        membership = db.execute(
            select(OrganisationMembership).where(OrganisationMembership.user_id == user.id)
        ).scalar_one_or_none()
        if membership is None:
            raise SystemExit(f"No organisation membership for {args.email}")

        org_id = membership.org_id
        if args.clear:
            removed = _clear_demo_orders(db, org_id)
            print(f"Cleared {removed} prior demo order(s).")

        if args.seed_hubspot_pool:
            added = _seed_hubspot_pool(db, org_id, CARE_REPAIR_CONTACTS)
            print(f"HubSpot local pool: upserted {len(CARE_REPAIR_CONTACTS)} contact(s) ({added} new).")

        wa_order = _create_order(
            db,
            org_id=org_id,
            user_id=user.id,
            channel="wa",
            title="Care & Repair · WhatsApp feedback (HubSpot demo)",
            contacts=wa_contacts,
        )
        call_order = _create_order(
            db,
            org_id=org_id,
            user_id=user.id,
            channel="ai_call",
            title="Care & Repair · AI call feedback (HubSpot demo)",
            contacts=call_contacts,
        )

        print("")
        print("Care & repair HubSpot demo surveys ready.")
        print(f"  Owner:           {args.email}")
        print(f"  WA order:        {wa_order.id}  ({len(wa_contacts)} completed)")
        print(f"  AI call order:   {call_order.id}  ({len(call_contacts)} completed)")
        print("")
        print("  Contacts (add matching emails in HubSpot CRM for sync):")
        for contact in CARE_REPAIR_CONTACTS:
            print(f"    - {contact['name']}: {contact['email']} · {contact['phone']} · {contact['channel']}")
        print("")
        print("  Dashboard:")
        print(f"    Surveys → Results → orderId={wa_order.id}")
        print(f"    Surveys → Results → orderId={call_order.id}")
        print("    More details → open respondent → Push result to HubSpot")
        print("")
        print("  Tip: Gmail plus-addresses (zaghlolno+careN@gmail.com) are distinct contacts in HubSpot.")

        if args.push_hubspot:
            print("")
            print("Pushing to HubSpot…")
            _push_results(db, org_id, [wa_order, call_order])


if __name__ == "__main__":
    main()
