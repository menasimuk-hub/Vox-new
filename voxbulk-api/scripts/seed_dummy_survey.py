#!/usr/bin/env python3
"""Seed a completed dummy AI-call survey with anonymous aggregate results.

Usage (server / local — must use the API virtualenv, not system python3):

  cd voxbulk-api
  source .venv/bin/activate
  python scripts/seed_dummy_survey.py

  # one-liner on VPS:
  .venv/bin/python scripts/seed_dummy_survey.py --email menasimuk@gmail.com

  # fix an existing broken demo order (unpaid / no results):
  .venv/bin/python scripts/seed_dummy_survey.py --repair ORDER_ID
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from sqlalchemy import select
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Missing Python dependencies (run inside voxbulk-api/.venv, not system python3):\n"
        "  cd /www/voxbulk/voxbulk-api\n"
        "  source .venv/bin/activate\n"
        "  python scripts/seed_dummy_survey.py\n"
        "Or: .venv/bin/python scripts/seed_dummy_survey.py"
    ) from exc

from app.core.database import get_sessionmaker
from app.models.membership import OrganisationMembership
from app.models.service_order import ServiceOrder
from app.models.user import User
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService
from app.services.survey_analysis_service import ANALYSIS_VERSION, refresh_order_survey_report
from app.services.survey_results_service import build_survey_results_payload

QUESTIONS = [
    "Overall satisfaction with our service?",
    "How likely are you to recommend us?",
    "How would you rate wait times?",
    "Was our staff friendly and helpful?",
    "What could we improve?",
]

ANSWER_OPTIONS = [
    ["Excellent", "Good", "Fair", "Poor"],
    ["9", "8", "7", "6", "5"],
    ["Very quick", "Acceptable", "A bit long", "Too long"],
    ["Yes, very helpful", "Mostly helpful", "Neutral", "Not really"],
    ["Nothing", "Faster booking", "Better parking", "Clearer pricing", "More appointment slots"],
]


def _build_script() -> str:
    lines = ["INTRO", "Hello, we are running a short anonymous survey.", "", "QUESTIONS"]
    for idx, q in enumerate(QUESTIONS, start=1):
        lines.append(f"{idx}. {q}")
    lines.extend(["", "CLOSING", "Thank you for your time."])
    return "\n".join(lines)


def _demo_config() -> dict:
    return {
        "survey_channel": "ai_call",
        "channels": ["call"],
        "contact_method": "AI phone call",
        "goal": "Patient experience and service quality",
        "organisation_name": "Demo Clinic",
        "survey_organiser_name": "Demo Organiser",
        "script_approved": True,
        "approved_script": _build_script(),
        "system_prompt": "Run a polite anonymous phone survey.",
    }


def _recipient_analysis(row_number: int) -> dict:
    rng = random.Random(row_number * 7919)
    answers = []
    for qi, question in enumerate(QUESTIONS):
        answer = rng.choice(ANSWER_OPTIONS[qi])
        answers.append({"question": question, "answer": answer, "confidence": "high"})
    recommend = int(answers[1]["answer"])
    sentiment = "positive" if recommend >= 8 else "neutral" if recommend >= 6 else "negative"
    sat = min(10, max(4, recommend + rng.randint(-1, 1)))
    return {
        "analysis": {
            "short_summary": "Anonymous respondent completed the survey.",
            "sentiment": sentiment,
            "satisfaction_score": sat,
            "recommend_score": recommend,
            "extracted_answers": answers,
            "issues": ["wait time"] if recommend < 7 and rng.random() > 0.5 else [],
            "tags": ["staff"] if sat >= 8 else [],
        },
        "analysis_saved_at": datetime.utcnow().isoformat(),
        "analysis_version": ANALYSIS_VERSION,
        "duration_seconds": rng.randint(120, 260),
        "transcript": "User: Thanks.\nAgent: Thank you for completing our anonymous survey.",
        "terminal_status": "completed",
    }


def _approve_payment_flow(db, order: ServiceOrder) -> ServiceOrder:
    """Quote → cash payment → admin approval (required before marking completed)."""
    if order.quote_total_pence <= 0 or order.status == "draft":
        order = ServiceOrderService.quote_order(db, order)
    if order.payment_status != "approved":
        if order.payment_status != "pending_approval":
            order = ServiceOrderService.submit_cash_payment(db, order, note="Dummy seed — cash payment")
        order = ServiceOrderService.admin_approve_payment(db, order, note="Dummy seed — auto approved")
    return order


def _populate_completed_recipients(db, order: ServiceOrder, *, completed: int) -> int:
    recipients = ServiceOrderService.get_recipients(db, order.id)
    if not recipients:
        raise SystemExit(f"Order {order.id} has no recipients — cannot seed results.")
    completed_target = min(completed, len(recipients))
    for recipient in recipients:
        if recipient.row_number <= completed_target:
            payload = _recipient_analysis(recipient.row_number)
            recipient.status = "completed"
            recipient.result_json = json.dumps(payload, ensure_ascii=False)
        elif recipient.row_number <= completed_target + 4:
            recipient.status = "no_answer"
            recipient.result_json = json.dumps({"terminal_status": "no_answer"})
        else:
            recipient.status = "pending"
            recipient.result_json = json.dumps({})
        db.add(recipient)
    db.commit()
    return completed_target


def _mark_order_finished(db, order: ServiceOrder) -> ServiceOrder:
    now = datetime.utcnow()
    order.payment_status = "approved"
    order.payment_method = order.payment_method or "cash"
    order.status = "completed"
    order.scheduled_start_at = order.scheduled_start_at or (now - timedelta(days=3))
    order.scheduled_end_at = order.scheduled_end_at or (now - timedelta(days=1))
    order.started_at = order.started_at or (now - timedelta(days=2))
    order.completed_at = now - timedelta(hours=6)
    order.updated_at = now
    db.add(order)
    db.commit()
    db.refresh(order)
    refresh_order_survey_report(db, order)
    db.refresh(order)
    return order


def _ensure_demo_config(order: ServiceOrder) -> None:
    try:
        config = json.loads(order.config_json or "{}")
    except Exception:
        config = {}
    if not config.get("survey_channel"):
        config.update(_demo_config())
        order.config_json = json.dumps(config, ensure_ascii=False)


def finalize_demo_order(db, order: ServiceOrder, *, completed: int = 32) -> ServiceOrder:
    _ensure_demo_config(order)
    db.add(order)
    db.commit()
    db.refresh(order)

    order = _approve_payment_flow(db, order)
    completed_target = _populate_completed_recipients(db, order, completed=completed)
    order = _mark_order_finished(db, order)

    try:
        payload = build_survey_results_payload(db, order, include_respondents=False)
        summary = payload.get("summary") or {}
        if int(summary.get("completed_count") or 0) <= 0:
            raise SystemExit("Seed finished but survey results payload has no completed responses.")
    except ValueError as exc:
        raise SystemExit(f"Seed finished but results API would fail: {exc}") from exc

    print("Dummy survey ready for results UI.")
    print(f"  Order ID:        {order.id}")
    print(f"  Title:           {order.title}")
    print(f"  Status:          {order.status} ({ServiceOrderService.survey_status_label(order)})")
    print(f"  Payment:         {order.payment_status}")
    print(f"  Completed calls: {completed_target}/{order.recipient_count}")
    print(f"  Report sent:     {(json.loads(order.report_json or '{}') or {}).get('completed', 0)}")
    print("Open Surveys → Finished tab → View report.")
    return order


def repair_order(db, order_id: str, *, completed: int = 32) -> ServiceOrder:
    order = db.get(ServiceOrder, order_id)
    if order is None:
        raise SystemExit(f"Order not found: {order_id}")
    if order.service_code != "survey":
        raise SystemExit(f"Order {order_id} is not a survey.")
    print(f"Repairing order {order.id} ({order.title})…")
    return finalize_demo_order(db, order, completed=completed)


def create_demo_order(db, *, org_id: str, user_id: str, contacts: int, completed: int) -> ServiceOrder:
    now = datetime.utcnow()
    order = ServiceOrderService.create_order(
        db,
        org_id=org_id,
        user_id=user_id,
        service_code="survey",
        title=f"Demo satisfaction survey · {now.strftime('%b %Y')}",
        config=_demo_config(),
    )

    rows = [
        {
            "name": f"Contact {i}",
            "phone": f"+447700900{i:03d}",
            "email": f"contact{i}@example.com",
        }
        for i in range(1, contacts + 1)
    ]
    ServiceOrderService.replace_recipients(db, order, rows)
    db.refresh(order)
    return finalize_demo_order(db, order, completed=completed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed or repair a completed demo survey with results")
    parser.add_argument("--email", default="menasimuk@gmail.com")
    parser.add_argument("--contacts", type=int, default=40)
    parser.add_argument("--completed", type=int, default=32)
    parser.add_argument("--repair", metavar="ORDER_ID", help="Fix an existing survey order (approve + fill results)")
    args = parser.parse_args()

    with get_sessionmaker()() as db:
        PlatformCatalogService.ensure_defaults(db)

        if args.repair:
            repair_order(db, args.repair, completed=args.completed)
            return

        user = db.execute(select(User).where(User.email == args.email)).scalar_one_or_none()
        if user is None:
            raise SystemExit(f"User not found: {args.email}")

        membership = db.execute(
            select(OrganisationMembership).where(OrganisationMembership.user_id == user.id)
        ).scalar_one_or_none()
        if membership is None:
            raise SystemExit(f"No organisation membership for {args.email}")

        order = create_demo_order(
            db,
            org_id=membership.org_id,
            user_id=user.id,
            contacts=args.contacts,
            completed=args.completed,
        )
        print(f"  User: {args.email}")


if __name__ == "__main__":
    main()
