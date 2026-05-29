#!/usr/bin/env python3
"""Seed dummy interview data for UI / field-gap testing.

Usage:
  cd voxbulk-api
  python scripts/seed_dummy_interview.py
  python scripts/seed_dummy_interview.py --email user@user.com --complete
  python scripts/seed_dummy_interview.py --repair ORDER_ID
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
        "Run inside voxbulk-api venv:\n"
        "  cd voxbulk-api\n"
        "  python scripts/seed_dummy_interview.py"
    ) from exc

from app.core.database import get_sessionmaker
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.services.interview_analysis_service import ANALYSIS_VERSION, refresh_order_interview_report
from app.services.interview_intake_service import (
    intake_contacts_merge,
    intake_summary,
    list_intake_recipients,
    recipient_intake_dict,
)
from app.services.interview_results_service import InterviewResultsService
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService

ROLE = "Senior Software Engineer"
CRITERIA = "Python, API design, distributed systems, clear communication, team leadership"

SCREENING_QUESTIONS = [
    "Tell me about your most recent backend project.",
    "How do you approach API design and versioning?",
    "Describe a time you debugged a production incident.",
    "What is your experience with async Python or event-driven systems?",
]


def _build_script() -> str:
    lines = [
        "INTRO",
        f"Hello, this is a screening call for the {ROLE} role.",
        "",
        "QUESTIONS",
    ]
    for idx, q in enumerate(SCREENING_QUESTIONS, start=1):
        lines.append(f"{idx}. {q}")
    lines.extend(["", "CLOSING", "Thank you for your time today."])
    return "\n".join(lines)


def _demo_config(org_name: str) -> dict:
    return {
        "role": ROLE,
        "criteria": CRITERIA,
        "screening_criteria": CRITERIA,
        "delivery": "ai_call",
        "organisation_name": org_name,
        "clinic_name": org_name,
        "organiser_name": "Demo Recruiter",
        "goal": f"Screen candidates for {ROLE}",
        "script_approved": True,
        "approved_script": _build_script(),
        "generated_script_draft": _build_script(),
        "system_prompt": "Run a professional phone screening interview.",
        "cv_email_enabled": False,
        "call_workflow": "screening",
    }


def _demo_contacts() -> list[dict[str, str | None]]:
    """Mix of complete rows + one missing phone to surface intake errors."""
    return [
        {"name": "Alice Chen", "phone": "+447700900101", "email": "alice.chen@example.com"},
        {"name": "Bob Martinez", "phone": "+447700900102", "email": "bob.m@example.com"},
        {"name": "Carol Singh", "phone": "+447700900103", "email": "carol.s@example.com"},
        {"name": "David Okonkwo", "phone": "+447700900104", "email": "david.o@example.com"},
        {"name": "Elena Rossi", "phone": "+447700900105", "email": "elena.r@example.com"},
        {"name": "Grace Kim", "phone": "+447700900107", "email": "grace.k@example.com"},
        {"name": "Henry Walsh", "phone": "+447700900108", "email": "henry.w@example.com"},
    ]


def _add_missing_phone_candidate(db, order: ServiceOrder) -> None:
    """Add one row with empty phone (DB NOT NULL — surfaces intake gap vs nullable model)."""
    recipients = ServiceOrderService.get_recipients(db, order.id)
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=len(recipients) + 1,
        name="Frank Unknown",
        phone="",
        email="frank@example.com",
        status="pending",
        cv_quality="missing",
        intake_source="csv",
        intake_errors_json=json.dumps(["Phone missing — click to add"], ensure_ascii=False),
    )
    db.add(recipient)
    order.recipient_count = len(recipients) + 1
    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()


def _enrich_cv_data(db, order: ServiceOrder) -> None:
    """Add CV + ATS fields on a subset of recipients (no file upload needed)."""
    recipients = ServiceOrderService.get_recipients(db, order.id)
    skills_pool = [
        ["Python", "FastAPI", "PostgreSQL", "Docker"],
        ["Python", "Django", "Redis", "AWS"],
        ["Java", "Spring", "Kafka"],
        ["TypeScript", "Node.js", "React"],
    ]
    for idx, recipient in enumerate(recipients):
        if not recipient.phone or idx % 2 == 0:
            continue
        skills = skills_pool[idx % len(skills_pool)]
        recipient.cv_quality = "good"
        recipient.cv_filename = f"{recipient.name.replace(' ', '_').lower()}_cv.pdf"
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
        recipient.ats_score = 62 + (idx * 7) % 35
        recipient.ats_status = "complete"
        recipient.intake_errors_json = json.dumps([], ensure_ascii=False)
        db.add(recipient)
    db.commit()


def _recipient_analysis(row_number: int, name: str) -> dict:
    rng = random.Random(row_number * 3571)
    score = rng.randint(58, 96)
    if score >= 85:
        recommendation, sentiment = "Advance", "Enthusiastic"
    elif score >= 72:
        recommendation, sentiment = "Hold", "Neutral"
    else:
        recommendation, sentiment = "Decline", "Hesitant"
    answers = []
    for q in SCREENING_QUESTIONS[:3]:
        answers.append(
            {
                "question": q,
                "answer": f"{name.split()[0]} gave a structured answer with concrete examples.",
                "quality": rng.choice(["strong", "adequate", "weak"]),
            }
        )
    duration = rng.randint(360, 720)
    transcript = (
        f"Agent: Hello {name}, thanks for joining.\n"
        f"Candidate: Happy to speak about the {ROLE} role.\n"
        + "\n".join(f"Agent: {q}\nCandidate: [detailed response]" for q in SCREENING_QUESTIONS)
        + "\nAgent: Thank you, we will be in touch."
    )
    return {
        "analysis": {
            "short_summary": f"{name} completed screening with score {score}.",
            "score": score,
            "recommendation": recommendation,
            "sentiment": sentiment,
            "strengths": ["Clear communication", "Relevant stack experience"],
            "concerns": [] if score >= 80 else ["Limited leadership examples"],
            "key_answers": answers,
            "completion_quality": "complete",
        },
        "analysis_saved_at": datetime.utcnow().isoformat(),
        "analysis_version": ANALYSIS_VERSION,
        "duration_seconds": duration,
        "transcript": transcript,
        "terminal_status": "completed",
        "call_summary": f"Screening completed — {recommendation}.",
        "call_control_id": f"demo-cc-{row_number:04d}",
        "provider": "telnyx_voice",
    }


def _seed_quote_fallback(db, order: ServiceOrder, *, per_candidate_pence: int = 320) -> ServiceOrder:
    """Set a synthetic quote when catalog pricing has duplicate-rule DB issues."""
    count = max(int(order.recipient_count or 0), 1)
    total = count * per_candidate_pence
    breakdown = {
        "lines": [
            {
                "kind": "interview",
                "label": "Dummy seed quote",
                "amount_pence": total,
                "detail": f"{count} candidates × £{per_candidate_pence / 100:.2f}",
            }
        ],
        "total_pence": total,
    }
    order.quote_total_pence = total
    order.quote_breakdown_json = json.dumps(breakdown, ensure_ascii=False)
    order.status = "quoted"
    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def _try_quote(db, order: ServiceOrder) -> ServiceOrder:
    try:
        return ServiceOrderService.quote_order(db, order)
    except Exception as exc:
        print(f"Quote via catalog failed ({exc}); using seed fallback quote.")
        return _seed_quote_fallback(db, order)


def _approve_payment_flow(db, order: ServiceOrder) -> ServiceOrder:
    if order.quote_total_pence <= 0 or order.status == "draft":
        order = _try_quote(db, order)
    if order.payment_status != "approved":
        if order.payment_status != "pending_approval":
            order = ServiceOrderService.submit_cash_payment(db, order, note="Dummy interview seed")
        order = ServiceOrderService.admin_approve_payment(db, order, note="Dummy interview seed — approved")
    return order


def _populate_completed_recipients(db, order: ServiceOrder, *, completed: int) -> int:
    recipients = ServiceOrderService.get_recipients(db, order.id)
    if not recipients:
        raise SystemExit(f"Order {order.id} has no recipients.")
    ready = [r for r in recipients if r.phone]
    completed_target = min(completed, len(ready))
    done = 0
    for recipient in recipients:
        if recipient.phone and done < completed_target:
            payload = _recipient_analysis(recipient.row_number, recipient.name or "Candidate")
            recipient.status = "completed"
            recipient.result_json = json.dumps(payload, ensure_ascii=False)
            done += 1
        elif not recipient.phone:
            recipient.status = "pending"
            recipient.result_json = json.dumps({"terminal_status": "pending"}, ensure_ascii=False)
        else:
            recipient.status = "no_answer"
            recipient.result_json = json.dumps({"terminal_status": "no_answer"}, ensure_ascii=False)
        db.add(recipient)
    db.commit()
    return done


def _mark_order_finished(db, order: ServiceOrder) -> ServiceOrder:
    now = datetime.utcnow()
    config = json.loads(order.config_json or "{}")
    recipients = ServiceOrderService.get_recipients(db, order.id)
    top_ids = [r.id for r in recipients if r.status == "completed"][:5]
    config["top_10_recipient_ids"] = top_ids
    config["shortlist_saved_at"] = now.isoformat()
    order.config_json = json.dumps(config, ensure_ascii=False)
    order.payment_status = "approved"
    order.payment_method = order.payment_method or "cash"
    order.status = "completed"
    order.scheduled_start_at = order.scheduled_start_at or (now - timedelta(days=2))
    order.scheduled_end_at = order.scheduled_end_at or (now - timedelta(days=1))
    order.started_at = order.started_at or (now - timedelta(days=1, hours=6))
    order.completed_at = now - timedelta(hours=2)
    order.updated_at = now
    db.add(order)
    db.commit()
    db.refresh(order)
    refresh_order_interview_report(db, order)
    db.refresh(order)
    return order


def audit_order(db, order: ServiceOrder) -> list[str]:
    """Printable list of missing / weak fields for gap testing."""
    warnings: list[str] = []
    config = json.loads(order.config_json or "{}")

    order_checks = {
        "reference_id": order.reference_id,
        "role": config.get("role"),
        "criteria": config.get("criteria") or config.get("screening_criteria"),
        "delivery": config.get("delivery"),
        "approved_script": config.get("approved_script"),
        "script_approved": config.get("script_approved"),
        "organisation_name": config.get("organisation_name"),
    }
    for key, value in order_checks.items():
        if value in (None, "", False):
            warnings.append(f"ORDER missing/empty: {key}")

    if order.recipient_count <= 0:
        warnings.append("ORDER: no recipients")
    if order.quote_total_pence <= 0 and order.status not in {"draft"}:
        warnings.append("ORDER: quote_total_pence is 0")

    recipients = list_intake_recipients(db, order)
    summary = intake_summary(recipients)
    if summary.get("missing_phone"):
        warnings.append(f"INTAKE: {summary['missing_phone']} candidate(s) missing phone")
    if summary.get("ready", 0) < summary.get("total", 0):
        warnings.append(f"INTAKE: only {summary['ready']}/{summary['total']} ready for quote")

    for r in recipients:
        label = r.get("name") or r.get("id")
        for err in r.get("intake_errors") or []:
            warnings.append(f"CANDIDATE {label}: {err}")
        if r.get("cv_quality") == "missing" and r.get("intake_ready"):
            warnings.append(f"CANDIDATE {label}: no CV (optional but may show empty in UI)")
        if r.get("ats_status") not in {"complete", "pending", "analyzing", None}:
            warnings.append(f"CANDIDATE {label}: ATS status {r.get('ats_status')}")

    if order.status == "completed":
        try:
            results = InterviewResultsService.get_results(db, order)
            if not results.get("candidates"):
                warnings.append("RESULTS: no candidates in results payload")
            if results.get("is_mock"):
                warnings.append("RESULTS: some candidates use mock scores (pending/no-answer rows)")
        except Exception as exc:
            warnings.append(f"RESULTS API error: {exc}")

    return warnings


def print_audit(db, order: ServiceOrder) -> None:
    warnings = audit_order(db, order)
    recipients = list_intake_recipients(db, order)
    summary = intake_summary(recipients)
    order_dict = ServiceOrderService.order_to_dict(order, include_recipients=False)

    print("\n=== Interview seed audit ===")
    print(f"Order ID:      {order.id}")
    print(f"Reference:     {order.reference_id or '—'}")
    print(f"Title:         {order.title}")
    print(f"Status:        {order.status} / payment {order.payment_status}")
    print(f"Quote:         £{order.quote_total_pence / 100:.2f}" if order.quote_total_pence else "Quote:         (not quoted)")
    print(f"Recipients:    {summary.get('total', 0)} total, {summary.get('ready', 0)} ready")
    print(f"CV good:       {summary.get('cv_good', 0)} | missing: {summary.get('cv_missing', 0)}")
    print(f"Config keys:   {', '.join(sorted((order_dict.get('config') or {}).keys())) or '—'}")

    if warnings:
        print("\nPotential gaps / issues:")
        for w in warnings:
            print(f"  - {w}")
    else:
        print("\nNo obvious field gaps detected.")

    print("\nOpen dashboard -> Interviews to review UI.")
    print(f"Results URL path: /service-orders/{order.id}/interview/results (authenticated)")


def finalize_completed(db, order: ServiceOrder, *, completed: int = 6) -> ServiceOrder:
    order = _approve_payment_flow(db, order)
    done = _populate_completed_recipients(db, order, completed=completed)
    order = _mark_order_finished(db, order)
    results = InterviewResultsService.get_results(db, order)
    advance = sum(1 for c in results.get("candidates") or [] if c.get("recommendation") == "Advance")
    print(f"Completed calls seeded: {done}/{order.recipient_count} | Advance: {advance}")
    return order


def _live_contacts() -> list[dict[str, str | None]]:
    return [
        {"name": "Alice Chen", "phone": "+447700900201", "email": "alice.chen@example.com"},
        {"name": "Bob Martinez", "phone": "+447700900202", "email": "bob.m@example.com"},
        {"name": "Carol Singh", "phone": "+447700900203", "email": "carol.s@example.com"},
        {"name": "David Okonkwo", "phone": "+447700900204", "email": "david.o@example.com"},
        {"name": "Elena Rossi", "phone": "+447700900205", "email": "elena.r@example.com"},
    ]


def _bootstrap_paid_order(db, *, org_id: str, user_id: str, org_name: str, title: str) -> ServiceOrder:
    order = ServiceOrderService.create_order(
        db,
        org_id=org_id,
        user_id=user_id,
        service_code="interview",
        title=title,
        config=_demo_config(org_name),
    )
    intake_contacts_merge(db, order, _live_contacts())
    db.refresh(order)
    _enrich_cv_data(db, order)
    db.refresh(order)
    order = _approve_payment_flow(db, order)
    return order


def create_finished_demo(db, *, org_id: str, user_id: str, org_name: str, label: str, completed: int = 5) -> ServiceOrder:
    now = datetime.utcnow()
    order = _bootstrap_paid_order(
        db,
        org_id=org_id,
        user_id=user_id,
        org_name=org_name,
        title=f"FINISHED · {ROLE} · {label} · {now.strftime('%d %b')}",
    )
    order = finalize_completed(db, order, completed=completed)
    print(f"  Finished: {order.id} ({order.title})")
    return order


def create_live_demo(db, *, org_id: str, user_id: str, org_name: str, mode: str, label: str) -> ServiceOrder:
    now = datetime.utcnow()
    order = _bootstrap_paid_order(
        db,
        org_id=org_id,
        user_id=user_id,
        org_name=org_name,
        title=f"LIVE · {mode.upper()} · {ROLE} · {label}",
    )
    recipients = ServiceOrderService.get_recipients(db, order.id)
    if mode == "running":
        order.status = "running"
        order.started_at = now - timedelta(hours=2)
        order.scheduled_start_at = now - timedelta(hours=3)
        order.scheduled_end_at = now + timedelta(hours=10)
        for idx, recipient in enumerate(recipients):
            if idx < 2:
                payload = _recipient_analysis(recipient.row_number, recipient.name or "Candidate")
                recipient.status = "completed"
                recipient.result_json = json.dumps(payload, ensure_ascii=False)
            elif idx == 2:
                recipient.status = "queued"
                recipient.result_json = json.dumps({"terminal_status": "queued"}, ensure_ascii=False)
            else:
                recipient.status = "pending"
                recipient.result_json = json.dumps(
                    {"terminal_status": "pending", "scheduling_sent_at": (now + timedelta(hours=idx)).isoformat()},
                    ensure_ascii=False,
                )
            db.add(recipient)
        order.report_json = json.dumps(
            {"completed": 2, "queued": 1, "pending": max(0, len(recipients) - 3), "total": len(recipients)},
            ensure_ascii=False,
        )
    else:
        order.status = "scheduled"
        order.scheduled_start_at = now + timedelta(days=1, hours=9)
        order.scheduled_end_at = now + timedelta(days=3, hours=17)
        for recipient in recipients:
            recipient.status = "pending"
            recipient.result_json = json.dumps(
                {"terminal_status": "pending", "scheduling_sent_at": order.scheduled_start_at.isoformat()},
                ensure_ascii=False,
            )
            db.add(recipient)
        order.report_json = json.dumps({"pending": len(recipients), "total": len(recipients)}, ensure_ascii=False)
    order.updated_at = now
    db.add(order)
    db.commit()
    db.refresh(order)
    refresh_order_interview_report(db, order)
    print(f"  Live ({mode}): {order.id} ({order.title})")
    return order


def seed_demo_set(db, *, org_id: str, user_id: str, org_name: str) -> list[ServiceOrder]:
    print("Creating demo set: 2 finished + 2 live interviews…")
    orders = [
        create_finished_demo(db, org_id=org_id, user_id=user_id, org_name=org_name, label="Batch A"),
        create_finished_demo(db, org_id=org_id, user_id=user_id, org_name=org_name, label="Batch B", completed=4),
        create_live_demo(db, org_id=org_id, user_id=user_id, org_name=org_name, mode="running", label="Active calls"),
        create_live_demo(db, org_id=org_id, user_id=user_id, org_name=org_name, mode="scheduled", label="Starts tomorrow"),
    ]
    return orders


def create_demo_order(
    db,
    *,
    org_id: str,
    user_id: str,
    org_name: str,
    complete: bool,
    completed: int,
) -> ServiceOrder:
    now = datetime.utcnow()
    order = ServiceOrderService.create_order(
        db,
        org_id=org_id,
        user_id=user_id,
        service_code="interview",
        title=f"Demo {ROLE} screening · {now.strftime('%b %Y')}",
        config=_demo_config(org_name),
    )
    intake_contacts_merge(db, order, _demo_contacts())
    _add_missing_phone_candidate(db, order)
    db.refresh(order)
    _enrich_cv_data(db, order)
    db.refresh(order)

    try:
        quoted = _try_quote(db, order)
        print(f"Quote OK: £{quoted.quote_total_pence / 100:.2f} for {quoted.recipient_count} candidates")
    except ValueError as exc:
        print(f"Quote blocked: {exc}")

    if complete:
        order = finalize_completed(db, order, completed=completed)
    return order


def repair_order(db, order_id: str, *, completed: int = 6) -> ServiceOrder:
    order = db.get(ServiceOrder, order_id)
    if order is None:
        raise SystemExit(f"Order not found: {order_id}")
    if order.service_code != "interview":
        raise SystemExit(f"Order {order_id} is not an interview.")
    print(f"Repairing interview {order.id} ({order.title})…")
    config = json.loads(order.config_json or "{}")
    if not config.get("role"):
        config.update(_demo_config("Demo Organisation"))
        order.config_json = json.dumps(config, ensure_ascii=False)
        db.add(order)
        db.commit()
        db.refresh(order)
    return finalize_completed(db, order, completed=completed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed dummy interview data for field/UI testing")
    parser.add_argument("--email", default="user@user.com", help="Dashboard user email")
    parser.add_argument("--complete", action="store_true", help="Also approve payment and seed completed results")
    parser.add_argument("--completed", type=int, default=6, help="How many candidates get completed call results")
    parser.add_argument("--repair", metavar="ORDER_ID", help="Fix an existing interview order")
    parser.add_argument(
        "--demo-set",
        action="store_true",
        help="Create 2 finished + 2 live interview campaigns (recommended for UI testing)",
    )
    args = parser.parse_args()

    with get_sessionmaker()() as db:
        try:
            PlatformCatalogService.ensure_defaults(db)
        except Exception as exc:
            print(f"Note: catalog defaults skipped ({exc})")

        if args.repair:
            order = repair_order(db, args.repair, completed=args.completed)
            print_audit(db, order)
            return

        user = db.execute(select(User).where(User.email == args.email)).scalar_one_or_none()
        if user is None:
            raise SystemExit(f"User not found: {args.email}")

        membership = db.execute(
            select(OrganisationMembership).where(OrganisationMembership.user_id == user.id)
        ).scalar_one_or_none()
        if membership is None:
            raise SystemExit(f"No organisation membership for {args.email}")

        org = db.get(Organisation, membership.org_id)
        org_name = (org.name if org else None) or "Demo Organisation"

        if args.demo_set:
            orders = seed_demo_set(db, org_id=membership.org_id, user_id=user.id, org_name=org_name)
            print(f"\nUser: {args.email} | Org: {org_name}")
            print(f"Created {len(orders)} interviews (2 finished, 2 live).")
            for order in orders:
                print_audit(db, order)
            return

        order = create_demo_order(
            db,
            org_id=membership.org_id,
            user_id=user.id,
            org_name=org_name,
            complete=args.complete,
            completed=args.completed,
        )
        print(f"\nUser: {args.email} | Org: {org_name}")
        print_audit(db, order)


if __name__ == "__main__":
    main()
