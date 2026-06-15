#!/usr/bin/env python3
"""Seed a rich demo account for any dashboard user — wallet debits included.

Creates three consolidated demo campaigns (one result each):
  • 100-member WhatsApp survey — fitness & gyms
  • 20-member AI phone survey — fitness & gyms
  • 20-candidate interview — 5 high ATS + call results (skipdaq@gmail.com success)

Usage:
  cd voxbulk-api && source .venv/bin/activate
  python scripts/seed_demo_user_account.py --email user@example.com --clear --auto-top-up
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import random
import sys
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
        "  source .venv/bin/activate && python scripts/seed_demo_user_account.py --email you@example.com"
    ) from exc


def _load_seed_module(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Could not load seed module: {path}")
    mod = importlib.util.module_from_spec(spec)
    # Required before exec_module: @dataclass reads sys.modules[cls.__module__]
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


mixed_seed = _load_seed_module("seed_demo_survey_mixed")
interview_seed = _load_seed_module("seed_dummy_interview")

from app.core.database import get_sessionmaker
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.survey_voice_note_job import SurveyVoiceNoteJob
from app.models.user import User
from app.services.billing_currency import money_display, resolve_org_currency
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService
from app.services.interview_analysis_service import refresh_order_interview_report
from app.services.survey_analysis_service import refresh_order_survey_report
from app.services.survey_launch_eligibility_service import (
    SurveyLaunchEligibilityError,
    SurveyLaunchEligibilityService,
)
from app.services.wallet_service import WalletService

# Reuse realistic mixed-result builders from existing seed scripts.
_demo_call_config = mixed_seed._demo_call_config
_demo_wa_config = mixed_seed._demo_wa_config
_mark_survey_finished = mixed_seed._mark_order_finished
_plan_respondent = mixed_seed._plan_respondent
_synthetic_contact = mixed_seed._synthetic_contact
_build_wa_payload = mixed_seed._build_wa_payload
_build_call_payload = mixed_seed._build_call_payload
_create_voice_jobs = mixed_seed._create_voice_jobs

ROLE = interview_seed.ROLE
_demo_config = interview_seed._demo_config
_mark_interview_finished = interview_seed._mark_order_finished
_recipient_analysis = interview_seed._recipient_analysis
_try_quote = interview_seed._try_quote
intake_contacts_merge = interview_seed.intake_contacts_merge

DEMO_ACCOUNT_PACK = "user_account_demo_v1"
DEMO_WA_MEMBERS = 100
DEMO_AI_CALL_MEMBERS = 20
DEMO_INTERVIEW_CANDIDATES = 20
DEMO_HIGH_ATS_COUNT = 5
DEFAULT_SUCCESS_EMAIL = "skipdaq@gmail.com"

GYM_BRANDS = (
    "PureGym",
    "David Lloyd",
    "The Gym Group",
    "Nuffield Health",
    "Fitness First",
    "Anytime Fitness",
    "Virgin Active",
    "Snap Fitness",
)


def _demo_wa_fitness_config() -> dict:
    cfg = dict(_demo_wa_config())
    cfg.update(
        {
            "goal": "Member feedback — fitness & gyms",
            "organisation_name": "FitLife Gyms",
            "survey_organiser_name": "Gym Member Experience",
            "industry": "fitness",
            "vertical": "gyms",
            "survey_topic": "gym_member_experience",
        }
    )
    return cfg


def _demo_ai_call_fitness_config() -> dict:
    cfg = dict(_demo_call_config())
    cfg.update(
        {
            "goal": "Member feedback — fitness & gyms (AI phone survey)",
            "organisation_name": "FitLife Gyms",
            "survey_organiser_name": "Gym Member Experience",
            "industry": "fitness",
            "vertical": "gyms",
        }
    )
    return cfg


def _fitness_wa_contact(index: int) -> dict[str, str]:
    brand = GYM_BRANDS[(index - 1) % len(GYM_BRANDS)]
    return {
        "name": f"{brand} · Member {index:03d}",
        "phone": f"+4477009{10000 + index:05d}",
        "email": f"gym.member.{index:03d}@example.invalid",
    }


def _enrich_all_ats(db, order: ServiceOrder, *, highlight_email: str | None = None) -> None:
    """Run ATS on every candidate with a phone number."""
    skills_pool = [
        ["Python", "FastAPI", "PostgreSQL", "Docker"],
        ["Python", "Django", "Redis", "AWS"],
        ["Java", "Spring", "Kafka"],
        ["TypeScript", "Node.js", "React"],
        ["Leadership", "Agile", "System design"],
    ]
    recipients = ServiceOrderService.get_recipients(db, order.id)
    for idx, recipient in enumerate(recipients):
        if not recipient.phone:
            continue
        skills = skills_pool[idx % len(skills_pool)]
        recipient.cv_quality = "excellent" if highlight_email and recipient.email == highlight_email else "good"
        recipient.cv_filename = f"{(recipient.name or 'candidate').replace(' ', '_').lower()}_cv.pdf"
        recipient.cv_text = (
            f"{recipient.name} — {ROLE} candidate. "
            f"Experience with {', '.join(skills)}. "
            "Led backend migrations and on-call rotations."
        )
        recipient.cv_parsed_json = json.dumps(
            {
                "skills": skills,
                "job_titles": ["Software Engineer", "Backend Developer"],
                "years_experience": 4 + (idx % 6),
            },
            ensure_ascii=False,
        )
        recipient.intake_source = "merged"
        recipient.ats_score = 94 if highlight_email and recipient.email == highlight_email else 62 + (idx * 7) % 35
        recipient.ats_status = "complete"
        recipient.intake_errors_json = json.dumps([], ensure_ascii=False)
        db.add(recipient)
    db.commit()


def _interview_contacts_batch(
    count: int,
    *,
    success_email: str | None = None,
) -> list[dict[str, str]]:
    contacts: list[dict[str, str]] = []
    for i in range(1, count + 1):
        if i == 1 and success_email:
            contacts.append(
                {
                    "name": "Skip Daq",
                    "phone": "+447700933001",
                    "email": success_email.strip().lower(),
                }
            )
            continue
        contacts.append(
            {
                "name": f"Demo Candidate {i:02d}",
                "phone": f"+4477009{30000 + i:05d}",
                "email": f"demo.interview.{i:02d}@example.invalid",
            }
        )
    return contacts


def _populate_survey_recipients(
    db,
    *,
    order: ServiceOrder,
    org_id: str,
    channel: str,
    member_count: int,
    seed: int,
) -> None:
    """Fill one survey order with mixed completed / unhappy / follow-up results."""
    rng = random.Random(seed)
    ch_key = "wa" if channel == "wa" else "ai_call"
    now = datetime.utcnow()
    recipients = ServiceOrderService.get_recipients(db, order.id)
    for recipient in recipients:
        idx = recipient.row_number or 1
        plan = _plan_respondent(idx, seed, channel=ch_key)
        # Ensure ~18% need follow-up for dashboard visibility on large WA runs
        if member_count >= 50 and idx % 6 == 0 and plan.status == "completed":
            plan = _plan_respondent(idx + 999, seed, channel=ch_key)
        started = now - timedelta(days=rng.randint(1, 10), hours=rng.randint(1, 8))
        completed = started + timedelta(minutes=rng.randint(3, 35)) if plan.status == "completed" else None

        if ch_key == "wa":
            payload, voice_jobs = _build_wa_payload(
                plan, index=idx, seed=seed, started_at=started, completed_at=completed
            )
            recipient.status = "no_answer" if plan.status == "no_answer" else ("failed" if plan.status == "failed" else plan.status)
            recipient.result_json = json.dumps(payload, ensure_ascii=False)
            if voice_jobs:
                _create_voice_jobs(
                    db,
                    org_id=org_id,
                    order_id=order.id,
                    recipient_id=recipient.id,
                    jobs=voice_jobs,
                    created_at=started,
                )
        else:
            if plan.status == "no_answer":
                recipient.status = "no_answer"
                payload = {"terminal_status": "no_answer"}
            elif plan.status == "failed":
                recipient.status = "failed"
                payload = {"terminal_status": "failed", "hangup_cause": "demo_failed"}
            else:
                recipient.status = plan.status
                payload = _build_call_payload(plan, index=idx, seed=seed, started_at=started, completed_at=completed)
            recipient.result_json = json.dumps(payload, ensure_ascii=False)
        db.add(recipient)
    db.commit()


def seed_consolidated_survey(
    db,
    *,
    org_id: str,
    user_id: str,
    org: Organisation,
    auto_top_up: bool,
    channel: str,
    member_count: int,
    title: str,
    seed: int,
) -> ServiceOrder:
    ch_key = "wa" if channel == "wa" else "ai_call"
    config = _tag_config(
        _demo_wa_fitness_config() if ch_key == "wa" else _demo_ai_call_fitness_config(),
        channel="survey",
    )
    order = ServiceOrderService.create_order(
        db,
        org_id=org_id,
        user_id=user_id,
        service_code="survey",
        title=title,
        config=config,
    )
    if ch_key == "wa":
        contacts = [_fitness_wa_contact(i) for i in range(1, member_count + 1)]
    else:
        contacts = [_synthetic_contact(i, channel="ai_call") for i in range(1, member_count + 1)]
    ServiceOrderService.replace_recipients(db, order, contacts)
    db.refresh(order)
    if ch_key == "ai_call":
        order = _prepare_ai_call_survey_for_launch(db, order, config)
    order = charge_survey_from_wallet(db, order, org, user_id=user_id, auto_top_up=auto_top_up)
    _populate_survey_recipients(
        db,
        order=order,
        org_id=org_id,
        channel=channel,
        member_count=member_count,
        seed=seed,
    )
    finished_channel = "whatsapp" if ch_key == "wa" else "ai_call"
    order = _mark_survey_finished(db, order, channel=finished_channel)
    refresh_order_survey_report(db, order)
    db.refresh(order)
    return order


def seed_consolidated_interview(
    db,
    *,
    org_id: str,
    user_id: str,
    org_name: str,
    org: Organisation,
    auto_top_up: bool,
    candidate_count: int,
    high_ats_count: int,
    success_email: str | None,
    seed: int,
) -> ServiceOrder:
    rng = random.Random(seed)
    contacts = _interview_contacts_batch(candidate_count, success_email=success_email)
    config = _tag_config(_demo_config(org_name))
    config["ats_skipped"] = False
    config["cv_min_ats_score"] = 65
    config["cv_email_enabled"] = True
    config["delivery"] = "ai_call"
    config["demo_account_pack"] = DEMO_ACCOUNT_PACK

    order = ServiceOrderService.create_order(
        db,
        org_id=org_id,
        user_id=user_id,
        service_code="interview",
        title=f"Demo Interview · {ROLE} · {candidate_count} candidates",
        config=config,
    )
    intake_contacts_merge(db, order, contacts)
    db.refresh(order)
    highlight = success_email.strip().lower() if success_email else None
    _enrich_all_ats(db, order, highlight_email=highlight)
    recipients = ServiceOrderService.get_recipients(db, order.id)
    high_ats_ids = {r.id for r in recipients[:high_ats_count] if r.phone}
    for idx, recipient in enumerate(recipients):
        if not recipient.phone:
            continue
        if recipient.id in high_ats_ids:
            recipient.ats_score = 88 + (idx % 8)
            recipient.ats_status = "complete"
            recipient.cv_quality = "excellent"
            db.add(recipient)
    db.commit()
    db.refresh(order)

    order = charge_interview_from_wallet(db, order, org, user_id=user_id, auto_top_up=auto_top_up)
    recipients = ServiceOrderService.get_recipients(db, order.id)
    highlight_norm = highlight
    for recipient in recipients:
        if not recipient.phone:
            recipient.status = "pending"
            recipient.result_json = json.dumps({"terminal_status": "pending"}, ensure_ascii=False)
            db.add(recipient)
            continue
        if recipient.id in high_ats_ids:
            payload = _recipient_analysis(recipient.row_number or 1, recipient.name or "Candidate")
            payload["analysis"]["score"] = int(recipient.ats_score or 90)
            payload["analysis"]["recommendation"] = "Advance"
            payload["analysis"]["sentiment"] = "Enthusiastic"
            if highlight_norm and str(recipient.email or "").strip().lower() == highlight_norm:
                payload["analysis"]["score"] = 94
                payload["analysis"]["short_summary"] = f"{recipient.name} — strong hire (demo success)."
                payload["call_summary"] = "Screening completed — Advance (demo success candidate)."
            recipient.status = "completed"
            recipient.result_json = json.dumps(payload, ensure_ascii=False)
        else:
            recipient.status = rng.choice(["completed", "no_answer", "queued"])
            if recipient.status == "completed":
                payload = _recipient_analysis(recipient.row_number or 1, recipient.name or "Candidate")
                recipient.result_json = json.dumps(payload, ensure_ascii=False)
            else:
                recipient.result_json = json.dumps({"terminal_status": recipient.status}, ensure_ascii=False)
        db.add(recipient)
    db.commit()

    order = _mark_interview_finished(db, order)
    refresh_order_interview_report(db, order)
    db.refresh(order)
    return order


def _tag_config(config: dict, *, channel: str | None = None) -> dict:
    tagged = dict(config)
    tagged["demo_account_pack"] = DEMO_ACCOUNT_PACK
    if channel == "survey":
        tagged["demo_survey_pack"] = DEMO_ACCOUNT_PACK
    return tagged


def _ensure_survey_agent_for_demo(db) -> str:
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.models.agent import AgentDefinition

    existing = db.execute(
        select(AgentDefinition)
        .where(
            AgentDefinition.is_active.is_(True),
            AgentDefinition.supports_survey.is_(True),
            AgentDefinition.telnyx_assistant_id.is_not(None),
            AgentDefinition.telnyx_assistant_id != "",
        )
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id

    by_slug = db.execute(
        select(AgentDefinition).where(AgentDefinition.slug == "demo-seed-survey-agent")
    ).scalar_one_or_none()
    telnyx_id = str(get_settings().survey_telnyx_assistant_id or "").strip() or "demo-seed-survey-assistant"
    now = datetime.utcnow()
    if by_slug is not None:
        if not str(by_slug.telnyx_assistant_id or "").strip():
            by_slug.telnyx_assistant_id = telnyx_id
        by_slug.supports_survey = True
        by_slug.is_active = True
        by_slug.updated_at = now
        db.add(by_slug)
        db.commit()
        return by_slug.id

    agent = AgentDefinition(
        name="Demo Survey Agent",
        slug="demo-seed-survey-agent",
        system_prompt="Demo seed survey caller.",
        supports_survey=True,
        is_active=True,
        is_default_survey=True,
        telnyx_assistant_id=telnyx_id,
        voice_label="Demo",
        created_at=now,
        updated_at=now,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent.id


def _prepare_ai_call_survey_for_launch(db, order: ServiceOrder, config: dict) -> ServiceOrder:
    """Phone surveys must pass launch eligibility (calling window + voice agent)."""
    now = datetime.utcnow()
    order.scheduled_start_at = order.scheduled_start_at or (now - timedelta(days=3))
    order.scheduled_end_at = order.scheduled_end_at or (now + timedelta(days=7))
    if order.scheduled_end_at <= order.scheduled_start_at:
        order.scheduled_end_at = order.scheduled_start_at + timedelta(days=4)

    tagged = dict(config)
    tagged["survey_agent_id"] = _ensure_survey_agent_for_demo(db)
    order.config_json = json.dumps(tagged, ensure_ascii=False)
    order.updated_at = now
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def ensure_wallet_balance(db, org: Organisation, *, needed_minor: int, auto_top_up: bool) -> int:
    """Return wallet balance after ensuring at least needed_minor is available."""
    currency = resolve_org_currency(db, org)
    balance = WalletService.balance_minor(org)
    if balance >= needed_minor:
        return balance
    shortfall = needed_minor - balance
    if not auto_top_up:
        raise SystemExit(
            f"Insufficient wallet for demo seed: need {money_display(needed_minor, currency)}, "
            f"have {money_display(balance, currency)}. Re-run with --auto-top-up or top up manually."
        )
    top_up = shortfall + 50_000  # £500 buffer for batch debits
    WalletService.credit(
        db,
        org,
        amount_minor=top_up,
        kind="manual_adjustment",
        description="Demo account seed — auto top-up",
        metadata={"script": "seed_demo_user_account.py"},
    )
    db.refresh(org)
    print(f"  Wallet topped up +{money_display(top_up, currency)} (balance now {money_display(WalletService.balance_minor(org), currency)})")
    return WalletService.balance_minor(org)


def charge_survey_from_wallet(db, order: ServiceOrder, org: Organisation, *, user_id: str, auto_top_up: bool) -> ServiceOrder:
    if order.payment_status == "approved":
        return order
    order = ServiceOrderService.quote_order(db, order)
    eligibility = SurveyLaunchEligibilityService.compute(db, order, org)
    breakdown = eligibility.get("launch_billing")
    if not isinstance(breakdown, dict):
        breakdown = {}
    wallet_charge = int(breakdown.get("wallet_charge_minor") or eligibility.get("amount_due_pence") or order.quote_total_pence or 0)
    if wallet_charge > 0:
        ensure_wallet_balance(db, org, needed_minor=wallet_charge, auto_top_up=auto_top_up)
    try:
        SurveyLaunchEligibilityService.approve_if_covered(db, order, org)
    except SurveyLaunchEligibilityError as exc:
        raise SystemExit(f"Survey wallet charge failed for {order.id}: {exc}") from exc
    db.refresh(order)
    return order


def charge_interview_from_wallet(db, order: ServiceOrder, org: Organisation, *, user_id: str, auto_top_up: bool) -> ServiceOrder:
    if order.payment_status == "approved":
        return order
    order = _try_quote(db, order)
    amount = int(order.quote_total_pence or 0)
    if amount > 0:
        ensure_wallet_balance(db, org, needed_minor=amount, auto_top_up=auto_top_up)
        WalletService.debit(
            db,
            org,
            amount_minor=amount,
            kind="launch_debit",
            description=f"Interview launch — {order.title}"[:500],
            order_id=order.id,
            created_by_user_id=user_id,
            metadata={"script": "seed_demo_user_account.py"},
        )
    order.payment_status = "approved"
    order.payment_method = "wallet"
    order.payment_note = f"Paid from wallet ({money_display(amount, resolve_org_currency(db, org))})"
    order.status = "paid"
    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def _clear_demo_orders(db, org_id: str) -> int:
    removed = 0
    orders = list(db.execute(select(ServiceOrder).where(ServiceOrder.org_id == org_id)).scalars())
    for order in orders:
        try:
            cfg = json.loads(order.config_json or "{}")
        except Exception:
            continue
        if cfg.get("demo_account_pack") != DEMO_ACCOUNT_PACK and cfg.get("demo_survey_pack") != DEMO_ACCOUNT_PACK:
            continue
        db.execute(delete(SurveyVoiceNoteJob).where(SurveyVoiceNoteJob.order_id == order.id))
        db.execute(delete(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id))
        db.delete(order)
        removed += 1
    if removed:
        db.commit()
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed consolidated demo campaigns with wallet debits")
    parser.add_argument("--email", required=True, help="Dashboard user email")
    parser.add_argument("--clear", action="store_true", help="Remove previous demo-account-pack orders first")
    parser.add_argument("--auto-top-up", action="store_true", help="Credit wallet if balance is insufficient")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    parser.add_argument("--wa-members", type=int, default=DEMO_WA_MEMBERS, help="WhatsApp members in one campaign")
    parser.add_argument("--ai-members", type=int, default=DEMO_AI_CALL_MEMBERS, help="AI call members in one campaign")
    parser.add_argument("--interview-candidates", type=int, default=DEMO_INTERVIEW_CANDIDATES, help="Interview candidates in one campaign")
    parser.add_argument("--high-ats", type=int, default=DEMO_HIGH_ATS_COUNT, help="High-ATS completed interview candidates")
    parser.add_argument("--success-email", default=DEFAULT_SUCCESS_EMAIL, help="Success interview candidate email")
    args = parser.parse_args()
    success_email = str(args.success_email or "").strip().lower() or None

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

        org = db.get(Organisation, membership.org_id)
        if org is None:
            raise SystemExit(f"Organisation not found: {membership.org_id}")
        org_name = org.name or "Demo Organisation"

        if args.clear:
            removed = _clear_demo_orders(db, membership.org_id)
            print(f"Cleared {removed} previous demo order(s) (pack={DEMO_ACCOUNT_PACK}).")

        currency = resolve_org_currency(db, org)
        start_balance = WalletService.balance_minor(org)
        print(f"\nUser: {args.email}")
        print(f"Org:  {org_name} ({org.id})")
        print(f"Wallet before: {money_display(start_balance, currency)}")

        print(f"\n1/3 Interview — {args.interview_candidates} candidates ({args.high_ats} high ATS)…")
        if success_email:
            print(f"     Success candidate: {success_email}")
        interview_order = seed_consolidated_interview(
            db,
            org_id=membership.org_id,
            user_id=user.id,
            org_name=org_name,
            org=org,
            auto_top_up=args.auto_top_up,
            candidate_count=args.interview_candidates,
            high_ats_count=min(args.high_ats, args.interview_candidates),
            success_email=success_email,
            seed=args.seed,
        )
        print(f"     {interview_order.title} · {interview_order.id} · £{interview_order.quote_total_pence / 100:.2f}")

        print(f"\n2/3 AI call survey — {args.ai_members} members (one campaign)…")
        ai_order = seed_consolidated_survey(
            db,
            org_id=membership.org_id,
            user_id=user.id,
            org=org,
            auto_top_up=args.auto_top_up,
            channel="ai_call",
            member_count=args.ai_members,
            title=f"Fitness & Gyms · AI Call Survey · {args.ai_members} members",
            seed=args.seed,
        )
        print(f"     {ai_order.title} · {ai_order.id} · £{ai_order.quote_total_pence / 100:.2f}")

        print(f"\n3/3 WhatsApp survey — {args.wa_members} members (one campaign)…")
        wa_order = seed_consolidated_survey(
            db,
            org_id=membership.org_id,
            user_id=user.id,
            org=org,
            auto_top_up=args.auto_top_up,
            channel="wa",
            member_count=args.wa_members,
            title=f"Fitness & Gyms · WhatsApp Survey · {args.wa_members} members",
            seed=args.seed + 1000,
        )
        print(f"     {wa_order.title} · {wa_order.id} · £{wa_order.quote_total_pence / 100:.2f}")

        db.refresh(org)
        end_balance = WalletService.balance_minor(org)
        debited = start_balance - end_balance
        print(f"\nWallet after:  {money_display(end_balance, currency)}")
        print(f"Total debited: {money_display(max(0, debited), currency)}")
        print("\nCreated 3 consolidated campaigns:")
        print(f"  Interview:  {interview_order.id} ({args.interview_candidates} candidates)")
        print(f"  AI survey:  {ai_order.id} ({args.ai_members} members)")
        print(f"  WA survey:  {wa_order.id} ({args.wa_members} members)")
        print("\nOpen dashboard home for sentiment / needs follow-up / live activity.")
        print("  Dashboard → /")
        print("  Surveys   → /surveys/results")
        print("  Interviews → /interviews/results")


if __name__ == "__main__":
    main()
