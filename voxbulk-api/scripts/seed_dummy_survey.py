#!/usr/bin/env python3
"""Seed a completed dummy AI-call survey with anonymous aggregate results.

Usage (server / local — must use the API virtualenv, not system python3):

  cd voxbulk-api
  source .venv/bin/activate
  python scripts/seed_dummy_survey.py

  # one-liner on VPS:
  .venv/bin/python scripts/seed_dummy_survey.py --email menasimuk@gmail.com
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
from app.models.user import User
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService
from app.services.survey_analysis_service import ANALYSIS_VERSION, refresh_order_survey_report

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed dummy completed survey with 40 contacts")
    parser.add_argument("--email", default="menasimuk@gmail.com")
    parser.add_argument("--contacts", type=int, default=40)
    parser.add_argument("--completed", type=int, default=32)
    args = parser.parse_args()

    with get_sessionmaker()() as db:
        PlatformCatalogService.ensure_defaults(db)
        user = db.execute(select(User).where(User.email == args.email)).scalar_one_or_none()
        if user is None:
            raise SystemExit(f"User not found: {args.email}")

        membership = db.execute(
            select(OrganisationMembership).where(OrganisationMembership.user_id == user.id)
        ).scalar_one_or_none()
        if membership is None:
            raise SystemExit(f"No organisation membership for {args.email}")

        config = {
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

        now = datetime.utcnow()
        order = ServiceOrderService.create_order(
            db,
            org_id=membership.org_id,
            user_id=user.id,
            service_code="survey",
            title=f"Demo satisfaction survey · {now.strftime('%b %Y')}",
            config=config,
        )

        rows = []
        for i in range(1, args.contacts + 1):
            rows.append(
                {
                    "name": f"Contact {i}",
                    "phone": f"+447700900{i:03d}",
                    "email": f"contact{i}@example.com",
                }
            )
        ServiceOrderService.replace_recipients(db, order, rows)
        db.refresh(order)
        order = ServiceOrderService.quote_order(db, order)
        order = ServiceOrderService.admin_approve_payment(db, order, note="Dummy seed — auto approved")
        order.scheduled_start_at = now - timedelta(days=3)
        order.scheduled_end_at = now - timedelta(days=1)
        order.started_at = now - timedelta(days=2)
        order.completed_at = now - timedelta(hours=6)
        order.status = "completed"
        order.payment_method = "cash"
        db.add(order)
        db.commit()
        db.refresh(order)

        recipients = ServiceOrderService.get_recipients(db, order.id)
        completed_target = min(args.completed, len(recipients))
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

        refresh_order_survey_report(db, order)
        print("Dummy survey created successfully.")
        print(f"  User:     {args.email}")
        print(f"  Order ID: {order.id}")
        print(f"  Title:    {order.title}")
        print(f"  Contacts: {len(recipients)} ({completed_target} completed)")
        print("Open Surveys → Finished tab → View results in the dashboard.")


if __name__ == "__main__":
    main()
