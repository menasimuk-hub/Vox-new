#!/usr/bin/env python3
"""Seed a rich demo account for any dashboard user — wallet debits included.

Creates mixed-result campaigns:
  • 20 AI call surveys
  • 20 interviews with ATS scores
  • 40 WhatsApp surveys

Usage:
  cd voxbulk-api && source .venv/bin/activate
  python scripts/seed_demo_user_account.py --email user@example.com
  python scripts/seed_demo_user_account.py --email user@example.com --clear
  python scripts/seed_demo_user_account.py --email user@example.com --auto-top-up
  python scripts/seed_demo_user_account.py --email user@example.com --ai 10 --interviews 5 --wa 20
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
_enrich_cv_data = interview_seed._enrich_cv_data
_mark_interview_finished = interview_seed._mark_order_finished
_recipient_analysis = interview_seed._recipient_analysis
_try_quote = interview_seed._try_quote
intake_contacts_merge = interview_seed.intake_contacts_merge

DEMO_ACCOUNT_PACK = "user_account_demo_v1"
DEFAULT_AI_COUNT = 20
DEFAULT_INTERVIEW_COUNT = 20
DEFAULT_WA_COUNT = 40


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


def _contacts_for_batch(index: int, *, channel: str, size: int) -> list[dict[str, str]]:
    base = index * 100
    return [_synthetic_contact(base + i, channel=channel) for i in range(1, size + 1)]


def seed_one_survey(
    db,
    *,
    org_id: str,
    user_id: str,
    channel: str,
    index: int,
    seed: int,
    org: Organisation,
    auto_top_up: bool,
) -> ServiceOrder:
    """Create one survey order, charge wallet, apply mixed recipient results."""
    rng = random.Random(seed + index)
    contact_count = rng.randint(4, 8)
    if channel == "wa":
        config = _tag_config(_demo_wa_config(), channel="survey")
        title = f"Demo WA · Batch {index:02d} · {contact_count} contacts"
        ch_key = "wa"
    else:
        config = _tag_config(_demo_call_config(), channel="survey")
        title = f"Demo AI Call · Batch {index:02d} · {contact_count} contacts"
        ch_key = "ai_call"

    order = ServiceOrderService.create_order(
        db,
        org_id=org_id,
        user_id=user_id,
        service_code="survey",
        title=title,
        config=config,
    )
    ServiceOrderService.replace_recipients(db, order, _contacts_for_batch(index, channel=ch_key, size=contact_count))
    db.refresh(order)
    if ch_key == "ai_call":
        order = _prepare_ai_call_survey_for_launch(db, order, config)
    order = charge_survey_from_wallet(db, order, org, user_id=user_id, auto_top_up=auto_top_up)

    now = datetime.utcnow()
    recipients = ServiceOrderService.get_recipients(db, order.id)
    for recipient in recipients:
        idx = recipient.row_number or 1
        plan = _plan_respondent(idx + index * 11, seed, channel=ch_key)
        started = now - timedelta(days=rng.randint(1, 14), hours=rng.randint(1, 10))
        completed = started + timedelta(minutes=rng.randint(3, 40)) if plan.status == "completed" else None

        if ch_key == "wa":
            payload, voice_jobs = _build_wa_payload(
                plan, index=idx, seed=seed + index, started_at=started, completed_at=completed
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
                payload = _build_call_payload(plan, index=idx, seed=seed + index, started_at=started, completed_at=completed)
            recipient.result_json = json.dumps(payload, ensure_ascii=False)
        db.add(recipient)

    db.commit()
    finished_channel = "ai_call" if ch_key == "ai_call" else "whatsapp"
    order = _mark_survey_finished(db, order, channel=finished_channel)

    # Mix order-level status for dashboard variety
    roll = rng.random()
    if roll < 0.12:
        order.status = "running"
        order.completed_at = None
    elif roll < 0.18:
        order.status = "scheduled"
        order.completed_at = None
        order.scheduled_start_at = now + timedelta(days=2)
        order.scheduled_end_at = now + timedelta(days=5)
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def seed_one_interview(
    db,
    *,
    org_id: str,
    user_id: str,
    org_name: str,
    index: int,
    seed: int,
    org: Organisation,
    auto_top_up: bool,
) -> ServiceOrder:
    rng = random.Random(seed + index * 3)
    contacts = [
        {
            "name": f"Demo Candidate {index:02d}-{i:02d}",
            "phone": f"+4477009{30000 + index * 10 + i:05d}",
            "email": f"demo.interview.{index:02d}.{i:02d}@example.invalid",
        }
        for i in range(1, rng.randint(4, 7))
    ]
    config = _tag_config(_demo_config(org_name))
    config["ats_skipped"] = False
    config["cv_min_ats_score"] = 65

    order = ServiceOrderService.create_order(
        db,
        org_id=org_id,
        user_id=user_id,
        service_code="interview",
        title=f"Demo Interview · {ROLE} · Batch {index:02d}",
        config=config,
    )
    intake_contacts_merge(db, order, contacts)
    db.refresh(order)
    _enrich_cv_data(db, order)
    db.refresh(order)
    order = charge_interview_from_wallet(db, order, org, user_id=user_id, auto_top_up=auto_top_up)

    completed_target = rng.randint(2, max(2, len(contacts) - 1))
    recipients = ServiceOrderService.get_recipients(db, order.id)
    done = 0
    for recipient in recipients:
        if recipient.phone and done < completed_target:
            payload = _recipient_analysis(recipient.row_number or done + 1, recipient.name or "Candidate")
            recipient.status = "completed"
            recipient.result_json = json.dumps(payload, ensure_ascii=False)
            done += 1
        elif not recipient.phone:
            recipient.status = "pending"
            recipient.result_json = json.dumps({"terminal_status": "pending"}, ensure_ascii=False)
        else:
            recipient.status = rng.choice(["no_answer", "queued", "pending"])
            recipient.result_json = json.dumps({"terminal_status": recipient.status}, ensure_ascii=False)
        db.add(recipient)
    db.commit()

    if rng.random() < 0.15:
        order.status = "running"
        order.completed_at = None
        order.started_at = datetime.utcnow() - timedelta(hours=3)
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    order = _mark_interview_finished(db, order)
    db.refresh(order)
    return order


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo account data with real wallet debits")
    parser.add_argument("--email", required=True, help="Dashboard user email")
    parser.add_argument("--clear", action="store_true", help="Remove previous demo-account-pack orders first")
    parser.add_argument("--auto-top-up", action="store_true", help="Credit wallet if balance is insufficient")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    parser.add_argument("--ai", type=int, default=DEFAULT_AI_COUNT, help="Number of AI call survey campaigns")
    parser.add_argument("--interviews", type=int, default=DEFAULT_INTERVIEW_COUNT, help="Number of interview campaigns")
    parser.add_argument("--wa", type=int, default=DEFAULT_WA_COUNT, help="Number of WhatsApp survey campaigns")
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

        created: list[tuple[str, ServiceOrder]] = []

        print(f"\nSeeding {args.ai} AI call surveys…")
        for i in range(1, args.ai + 1):
            order = seed_one_survey(
                db,
                org_id=membership.org_id,
                user_id=user.id,
                channel="ai_call",
                index=i,
                seed=args.seed,
                org=org,
                auto_top_up=args.auto_top_up,
            )
            created.append(("AI Call", order))
            print(f"  [{i}/{args.ai}] {order.title} · {order.id} · £{order.quote_total_pence / 100:.2f}")

        print(f"\nSeeding {args.interviews} interviews with ATS…")
        for i in range(1, args.interviews + 1):
            order = seed_one_interview(
                db,
                org_id=membership.org_id,
                user_id=user.id,
                org_name=org_name,
                index=i,
                seed=args.seed,
                org=org,
                auto_top_up=args.auto_top_up,
            )
            created.append(("Interview", order))
            print(f"  [{i}/{args.interviews}] {order.title} · {order.id} · £{order.quote_total_pence / 100:.2f}")

        print(f"\nSeeding {args.wa} WhatsApp surveys…")
        for i in range(1, args.wa + 1):
            order = seed_one_survey(
                db,
                org_id=membership.org_id,
                user_id=user.id,
                channel="wa",
                index=i,
                seed=args.seed + 1000,
                org=org,
                auto_top_up=args.auto_top_up,
            )
            created.append(("WhatsApp", order))
            print(f"  [{i}/{args.wa}] {order.title} · {order.id} · £{order.quote_total_pence / 100:.2f}")

        db.refresh(org)
        end_balance = WalletService.balance_minor(org)
        debited = start_balance - end_balance
        print(f"\nWallet after:  {money_display(end_balance, currency)}")
        print(f"Total debited: {money_display(max(0, debited), currency)}")
        print(f"\nCreated {len(created)} campaigns — open Dashboard to review.")
        print("  Surveys  → /surveys")
        print("  Interviews → /interviews")


if __name__ == "__main__":
    main()
