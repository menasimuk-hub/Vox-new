#!/usr/bin/env python3
"""Seed Customer Feedback QR survey results (happy + unhappy mix) for dashboard QA.

Inserts completed FeedbackSession + FeedbackResponse rows directly — no WhatsApp/Telnyx.

Usage:
  cd voxbulk-api && source .venv/bin/activate
  python scripts/seed_feedback_responses_mixed.py --email zaghlolno@gmail.com --count 100

  python scripts/seed_feedback_responses_mixed.py --email zaghlolno@gmail.com --clear
  python scripts/seed_feedback_responses_mixed.py --email zaghlolno@gmail.com --location-id UUID --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from sqlalchemy import delete, select
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Run inside voxbulk-api/.venv:\n"
        "  source .venv/bin/activate && python scripts/seed_feedback_responses_mixed.py"
    ) from exc

from app.core.database import get_sessionmaker
from app.models.customer_feedback import FeedbackLocation, FeedbackResponse, FeedbackSession, FeedbackWaTemplate
from app.models.membership import OrganisationMembership
from app.models.user import User
from app.services.customer_feedback.feedback_answer_service import POOR_ANSWERS
from app.services.customer_feedback.feedback_results_aggregate import classify_pge, classify_yn
from app.services.customer_feedback.results_service import FeedbackResultsService
from app.services.customer_feedback.seed_service import FeedbackSeedService
from app.services.customer_feedback.survey_config_service import (
    get_system_template,
    load_survey_config,
    template_for_step,
)
from app.services.customer_feedback.whatsapp_service import FeedbackWhatsappService

DEFAULT_EMAIL = "zaghlolno@gmail.com"
DEFAULT_COUNT = 100
DEFAULT_SEED = 42
PHONE_PREFIX = "+44770099"  # synthetic: +447700990000 … +447700990099

HAPPY_OPEN = [
    "Very smooth visit — staff were brilliant.",
    "WhatsApp reminder made check-in easy.",
    "Great experience overall, will come again.",
    "Friendly team and quick service today.",
]
UNHAPPY_OPEN = [
    "Waited too long and nobody explained the delay.",
    "Insurance process was confusing at reception.",
    "Felt rushed and the bill was higher than quoted.",
    "Waiting room was crowded — needs improvement.",
]
TELL_US_MORE = [
    "I waited almost forty minutes past my appointment time.",
    "No one apologised for the delay or explained why.",
    "Reception gave me different information than the phone line.",
]


def _parse_buttons(tpl: FeedbackWaTemplate | None) -> list[str]:
    if tpl is None or not tpl.buttons_json:
        return []
    try:
        parsed = json.loads(tpl.buttons_json)
        if isinstance(parsed, list):
            return [str(b).strip() for b in parsed if str(b).strip()]
    except json.JSONDecodeError:
        pass
    return []


def _positive_button(buttons: list[str]) -> str:
    for label in buttons:
        low = label.lower()
        if classify_pge(label) in {"excellent", "good"} or classify_yn(label) == "yes":
            return label
        if any(w in low for w in ("excellent", "great", "very", "definitely", "loved", "quick", "fast", "clean")):
            return label
    return buttons[0] if buttons else "Excellent"


def _negative_button(buttons: list[str]) -> str:
    for label in buttons:
        low = label.lower()
        if classify_pge(label) == "poor" or classify_yn(label) == "no":
            return label
        if low in POOR_ANSWERS or any(w in low for w in ("poor", "slow", "long", "unlikely", "unfriendly", "overpriced")):
            return label
    return buttons[-1] if buttons else "Poor"


def _answer_for_template(tpl: FeedbackWaTemplate | None, *, happy: bool) -> tuple[str, str]:
    """Return (answer_text_en, original_text)."""
    role = str(tpl.step_role if tpl else "").lower()
    buttons = _parse_buttons(tpl)

    if role == "rating":
        word = "excellent" if happy else "poor"
        return word, word.capitalize()
    if role in {"yes_no", "marketing_opt_in"}:
        word = "yes" if happy else "no"
        if buttons:
            pick = _positive_button(buttons) if happy else _negative_button(buttons)
            return word, pick
        return word, word.capitalize()
    if role in {"final_feedback_text", "tell_us_more", "open", "reason"}:
        text = random.choice(HAPPY_OPEN if happy else (TELL_US_MORE if role == "tell_us_more" else UNHAPPY_OPEN))
        return text, text
    if buttons:
        pick = _positive_button(buttons) if happy else _negative_button(buttons)
        en = classify_pge(pick) or classify_yn(pick) or pick.lower()
        return str(en), pick
    return ("excellent" if happy else "poor"), ("Excellent" if happy else "Poor")


def _answerable_steps(db, location: FeedbackLocation) -> list[dict[str, Any]]:
    steps = FeedbackWhatsappService._steps_for_location(db, location)
    out: list[dict[str, Any]] = []
    for step in steps:
        kind = str(step.get("kind") or "")
        if kind in {"topic", "open_question", "marketing_opt_in"}:
            out.append(step)
    return out


def _resolve_org_id(db, email: str, org_id: str | None) -> str:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        raise SystemExit(f"No user found for email: {email}")
    memberships = list(
        db.execute(select(OrganisationMembership).where(OrganisationMembership.user_id == user.id)).scalars().all()
    )
    if not memberships:
        raise SystemExit(f"User {email} has no organisation membership.")
    if org_id:
        if not any(m.org_id == org_id for m in memberships):
            raise SystemExit(f"User {email} is not a member of org {org_id}.")
        return org_id
    if len(memberships) > 1:
        print(f"Note: {email} belongs to {len(memberships)} orgs — using {memberships[0].org_id}")
    return memberships[0].org_id


def _pick_location(db, org_id: str, location_id: str | None) -> FeedbackLocation:
    q = select(FeedbackLocation).where(FeedbackLocation.org_id == org_id).order_by(FeedbackLocation.name)
    if location_id:
        q = q.where(FeedbackLocation.id == location_id)
    loc = db.execute(q.limit(1)).scalar_one_or_none()
    if loc is None:
        raise SystemExit(
            "No Customer Feedback location found for this org. "
            "Create a QR survey in Dashboard → Customer Feedback first."
        )
    return loc


def _clear_seeded(db, org_id: str, location_id: str) -> int:
    sessions = list(
        db.execute(
            select(FeedbackSession).where(
                FeedbackSession.org_id == org_id,
                FeedbackSession.location_id == location_id,
                FeedbackSession.visitor_phone.like(f"{PHONE_PREFIX}%"),
            )
        ).scalars().all()
    )
    if not sessions:
        return 0
    ids = [s.id for s in sessions]
    db.execute(delete(FeedbackResponse).where(FeedbackResponse.session_id.in_(ids)))
    db.execute(delete(FeedbackSession).where(FeedbackSession.id.in_(ids)))
    db.commit()
    return len(sessions)


def seed_respondents(
    *,
    email: str,
    count: int,
    seed: int,
    location_id: str | None,
    org_id: str | None,
    clear: bool,
    unhappy_pct: int,
) -> None:
    random.seed(seed)
    FeedbackSeedService.ensure_seeded(get_sessionmaker()())

    with get_sessionmaker()() as db:
        resolved_org = _resolve_org_id(db, email, org_id)
        location = _pick_location(db, resolved_org, location_id)
        steps = _answerable_steps(db, location)
        if not steps:
            raise SystemExit(f"Location {location.name} has no answerable survey steps.")

        if clear:
            removed = _clear_seeded(db, resolved_org, location.id)
            if removed:
                print(f"Cleared {removed} prior seeded session(s).")

        now = datetime.utcnow()
        unhappy_target = max(1, round(count * unhappy_pct / 100))
        unhappy_indices = set(random.sample(range(count), k=min(unhappy_target, count)))

        created = 0
        for i in range(count):
            happy = i not in unhappy_indices
            phone = f"{PHONE_PREFIX}{i:04d}"
            days_ago = random.randint(0, 56)
            started = now - timedelta(days=days_ago, hours=random.randint(1, 20), minutes=random.randint(0, 59))
            completed = started + timedelta(minutes=random.randint(3, 25))

            session = FeedbackSession(
                id=str(uuid.uuid4()),
                org_id=resolved_org,
                location_id=location.id,
                visitor_phone=phone,
                status="completed",
                current_step=len(steps),
                detected_language="en_GB",
                trigger_dedupe_key=f"{phone}:{location.qr_token}",
                started_at=started,
                completed_at=completed,
                created_at=started,
            )
            db.add(session)
            db.flush()  # ensure session row exists before responses (MySQL FK)

            step_order = 0
            had_poor = False
            for step in steps:
                tpl = template_for_step(db, location, step, language="en_GB")
                if tpl is None and step.get("kind") == "open_question":
                    tpl = get_system_template(db, "open_question", language="en_GB")
                if tpl is None:
                    continue
                answer_en, original = _answer_for_template(tpl, happy=happy)
                if classify_pge(answer_en) == "poor" or classify_yn(answer_en) == "no":
                    had_poor = True
                step_order += 1
                survey_type_id = str(step.get("survey_type_id") or location.survey_type_id)
                db.add(
                    FeedbackResponse(
                        id=str(uuid.uuid4()),
                        session_id=session.id,
                        org_id=resolved_org,
                        location_id=location.id,
                        survey_type_id=survey_type_id,
                        question_key=tpl.template_key,
                        answer_text=answer_en,
                        answer_text_en=answer_en,
                        original_text=original,
                        step_order=step_order,
                        answer_source="text",
                        created_at=completed,
                    )
                )

            if not happy and had_poor:
                tell_more = get_system_template(db, "tell_us_more", language="en_GB")
                if tell_more:
                    text = random.choice(TELL_US_MORE)
                    step_order += 1
                    db.add(
                        FeedbackResponse(
                            id=str(uuid.uuid4()),
                            session_id=session.id,
                            org_id=resolved_org,
                            location_id=location.id,
                            survey_type_id=str(location.survey_type_id),
                            question_key=tell_more.template_key,
                            answer_text=text,
                            answer_text_en=text,
                            original_text=text,
                            step_order=step_order,
                            answer_source="text",
                            created_at=completed,
                        )
                    )

            created += 1
            if created % 25 == 0:
                db.commit()
                print(f"  … {created}/{count} respondents saved")

        location.scan_count = max(int(location.scan_count or 0), count + 20)
        db.add(location)
        db.commit()

        payload = FeedbackResultsService.customer_results(db, resolved_org, location_id=location.id)
        summary = payload.get("summary") or {}
        respondents = payload.get("respondents") or []

        print()
        print("Customer Feedback demo seed complete")
        print(f"  Email:        {email}")
        print(f"  Org:          {resolved_org}")
        print(f"  Location:     {location.name} ({location.id})")
        print(f"  Respondents:  {created} inserted ({len(unhappy_indices)} unhappy / {count - len(unhappy_indices)} happy)")
        print(f"  Completed:    {summary.get('completed_sessions', '—')}")
        print(f"  Unhappy:      {summary.get('unhappy_count', '—')}")
        print(f"  Satisfaction: {summary.get('satisfaction_pct', '—')}%")
        print(f"  In results:   {len(respondents)} respondent row(s)")
        print()
        print("Open Dashboard → Customer Feedback → Results (filter by this location).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed mixed Customer Feedback results for dashboard QA")
    parser.add_argument("--email", default=DEFAULT_EMAIL, help=f"Dashboard user email (default: {DEFAULT_EMAIL})")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help="Number of respondents (default: 100)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="RNG seed for reproducible mix")
    parser.add_argument("--location-id", default=None, help="Feedback location UUID (default: first for org)")
    parser.add_argument("--org-id", default=None, help="Organisation UUID when user has multiple orgs")
    parser.add_argument("--unhappy-pct", type=int, default=40, help="Percent unhappy respondents (default: 40)")
    parser.add_argument("--clear", action="store_true", help=f"Remove prior seeded sessions ({PHONE_PREFIX}*)")
    args = parser.parse_args()
    if args.count < 1 or args.count > 9999:
        raise SystemExit("--count must be between 1 and 9999")
    if not 0 <= args.unhappy_pct <= 100:
        raise SystemExit("--unhappy-pct must be 0–100")

    seed_respondents(
        email=args.email.strip().lower(),
        count=args.count,
        seed=args.seed,
        location_id=args.location_id,
        org_id=args.org_id,
        clear=args.clear,
        unhappy_pct=args.unhappy_pct,
    )


if __name__ == "__main__":
    main()
