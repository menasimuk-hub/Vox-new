#!/usr/bin/env python3
"""Seed realistic mixed demo data for WA Survey and AI Call Survey reporting QA.

Synthetic contacts only — no real personal data.

Usage:
  cd voxbulk-api && source .venv/bin/activate
  python scripts/seed_demo_survey_mixed.py --email you@example.com

  python scripts/seed_demo_survey_mixed.py --email user@user.com --clear
  python scripts/seed_demo_survey_mixed.py --wa-only --count 50
  python scripts/seed_demo_survey_mixed.py --call-only --seed 42
  python scripts/seed_demo_survey_mixed.py --export-json /tmp/demo_survey.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import uuid
from dataclasses import dataclass
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
        "  source .venv/bin/activate && python scripts/seed_demo_survey_mixed.py"
    ) from exc

from app.core.database import get_sessionmaker
from app.models.membership import OrganisationMembership
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.survey_voice_note_job import SurveyVoiceNoteJob
from app.models.user import User
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService
from app.services.survey_analysis_service import ANALYSIS_VERSION, refresh_order_survey_report
from app.services.survey_results_service import (
    build_survey_results_payload,
    build_whatsapp_survey_results_payload,
)

DEMO_PACK_ID = "mixed_responses_demo_v1"
DEFAULT_SEED = 42
DEFAULT_COUNT = 100

WA_QUESTIONS = [
    {
        "id": "q1_reach",
        "order": 1,
        "text": "Did we reach you successfully?",
        "answer_type": "choice",
        "options": ["Yes", "No"],
        "step_role": "reach",
    },
    {
        "id": "q2_experience",
        "order": 2,
        "text": "How was your overall experience?",
        "answer_type": "choice",
        "options": ["Bad", "Good", "Excellent"],
        "step_role": "experience",
    },
    {
        "id": "q3_resolved",
        "order": 3,
        "text": "Was your issue resolved?",
        "answer_type": "choice",
        "options": ["Yes", "No"],
        "step_role": "resolved",
    },
    {
        "id": "q4_share",
        "order": 4,
        "text": "Would you like to share your experience?",
        "answer_type": "open",
        "step_role": "final_feedback_text",
    },
]

CALL_QUESTIONS = [
    {
        "id": "q1_happy",
        "order": 1,
        "text": "Were you happy to take this call?",
        "answer_type": "choice",
        "options": ["Yes", "No"],
    },
    {
        "id": "q2_rate",
        "order": 2,
        "text": "How would you rate the experience?",
        "answer_type": "choice",
        "options": ["Bad", "Good", "Excellent"],
    },
    {
        "id": "q3_understood",
        "order": 3,
        "text": "Did we understand your needs correctly?",
        "answer_type": "choice",
        "options": ["Yes", "No"],
    },
    {
        "id": "q4_tell_more",
        "order": 4,
        "text": "Please tell us more about your experience",
        "answer_type": "open",
    },
]

NEGATIVE_TAGS = ["delay", "rude_staff", "no_response", "poor_service", "billing_issue", "booking_issue"]
POSITIVE_TAGS = ["friendly_staff", "quick_service", "helpful_team", "satisfied", "resolved"]

WA_TEXT_FEEDBACK = [
    "Waited twenty minutes past my slot. Reception didn't apologise.",
    "Booking link never arrived. Had to call twice.",
    "Staff were lovely once I got through — just slow at the desk.",
    "Charged twice on the invoice. Needs fixing.",
    "All fine, nothing else to add.",
    "Parking was a nightmare but the nurse was brilliant.",
    "Nobody called me back about my complaint.",
    "Quick visit, in and out. Happy overall.",
    "The follow-up email was really helpful.",
    "Bit rushed but professional.",
]

WA_VOICE_TRANSCRIPTS = [
    "Um yeah so I waited ages in the waiting room and nobody told me what was happening.",
    "Hi yeah the team were actually really kind but the booking system sent me the wrong time.",
    "So basically I am still waiting for someone to call me back about my bill.",
    "Yeah no issues really just wanted to say thank you to the receptionist she was great.",
    "I'm not happy I was spoken to quite rudely at check in.",
]

CALL_TEXT_FEEDBACK = [
    (
        "I appreciated the call. The agent listened properly and repeated my answers back. "
        "The only thing I'd change is sending a confirmation text sooner."
    ),
    (
        "Honestly I wasn't expecting a survey call but it was fine. "
        "My appointment was moved twice and I'm still unclear why the first slot was cancelled."
    ),
    (
        "Really impressed — felt like a proper conversation not a script. "
        "I'd recommend you to a friend based on how this call was handled."
    ),
    (
        "The person on the phone didn't seem to understand my issue about the invoice. "
        "I explained three times that I'd already paid online and they kept asking for card details."
    ),
    (
        "Neutral really. Service was okay. Parking is still a pain and that's my main gripe."
    ),
    (
        "Thank you for checking in. The nurse last week was exceptional — professional and warm. "
        "That made a difficult visit much easier for my mother."
    ),
]

CALL_VOICE_TRANSCRIPTS = [
    (
        "Yeah so um I mean the call itself was alright but I still haven't had anyone follow up "
        "about the refund I asked for last month."
    ),
    (
        "Oh it's fine yeah — actually the lady who called was really patient with me "
        "because I had to find my reference number."
    ),
]


@dataclass
class RespondentPlan:
    status: str
    answers_count: int
    q1: str | None
    q2: str | None
    q3: str | None
    open_mode: str | None  # text | voice | None
    sentiment: str
    needs_follow_up: bool
    tags: list[str]
    issues: list[str]


def _rng_for(index: int, seed: int) -> random.Random:
    return random.Random(seed * 1_000_003 + index * 9_173)


def _pick_weighted(rng: random.Random, pairs: list[tuple[Any, float]]) -> Any:
    total = sum(w for _, w in pairs)
    roll = rng.random() * total
    acc = 0.0
    for value, weight in pairs:
        acc += weight
        if roll <= acc:
            return value
    return pairs[-1][0]


def _plan_respondent(index: int, seed: int, *, channel: str) -> RespondentPlan:
    rng = _rng_for(index, seed)
    archetype = _pick_weighted(
        rng,
        [
            ("completed_positive", 0.28),
            ("completed_neutral", 0.18),
            ("completed_negative_text", 0.14),
            ("completed_negative_voice", 0.10),
            ("completed_negative_strong", 0.08),
            ("partial_q2", 0.08),
            ("partial_q3", 0.06),
            ("no_answer", 0.10),
            ("failed", 0.04),
            ("in_progress", 0.04),
        ],
    )

    if archetype == "no_answer":
        return RespondentPlan("no_answer", 0, None, None, None, None, "neutral", False, [], [])
    if archetype == "failed":
        return RespondentPlan("failed", 0, None, None, None, None, "negative", False, [], [])
    if archetype == "in_progress":
        q1 = rng.choice(["Yes", "No"])
        return RespondentPlan("in_progress", 1, q1, None, None, None, "neutral", False, [], [])
    if archetype == "partial_q2":
        q1 = "Yes" if rng.random() > 0.15 else "No"
        q2 = _pick_weighted(rng, [("Bad", 0.35), ("Good", 0.45), ("Excellent", 0.20)])
        return RespondentPlan("in_progress", 2, q1, q2, None, None, _sentiment_from_q2(q2), False, [], [])
    if archetype == "partial_q3":
        q1 = "Yes"
        q2 = _pick_weighted(rng, [("Bad", 0.25), ("Good", 0.50), ("Excellent", 0.25)])
        q3 = "No" if q2 == "Bad" else rng.choice(["Yes", "No"])
        return RespondentPlan("in_progress", 3, q1, q2, q3, None, _sentiment_from_q2(q2), q2 == "Bad", _tags_for(q2, q3, rng), _issues_for(q2, q3, rng))

    q1 = "Yes" if rng.random() > 0.12 else "No"
    q2 = _pick_weighted(
        rng,
        [("Bad", 0.22), ("Good", 0.48), ("Excellent", 0.30)] if archetype != "completed_negative_strong" else [("Bad", 0.75), ("Good", 0.20), ("Excellent", 0.05)],
    )
    q3 = "No" if q2 == "Bad" else ("Yes" if rng.random() > 0.25 else "No")
    negative = q2 == "Bad" or q3 == "No"

    open_mode = None
    if archetype == "completed_negative_text":
        open_mode = "text"
    elif archetype == "completed_negative_voice":
        open_mode = "voice"
    elif archetype == "completed_negative_strong":
        open_mode = "voice" if rng.random() > 0.4 else "text"
    elif negative and rng.random() > 0.45:
        open_mode = "voice" if rng.random() > 0.55 else "text"
    elif not negative and rng.random() > 0.78:
        open_mode = "text" if rng.random() > 0.35 else ("voice" if channel == "wa" and rng.random() > 0.6 else "text")

    sentiment = _sentiment_from_q2(q2)
    needs_follow_up = negative and (open_mode is not None or q3 == "No")
    tags = _tags_for(q2, q3, rng)
    issues = _issues_for(q2, q3, rng)

    return RespondentPlan("completed", 4, q1, q2, q3, open_mode, sentiment, needs_follow_up, tags, issues)


def _sentiment_from_q2(q2: str | None) -> str:
    if q2 == "Excellent":
        return "positive"
    if q2 == "Good":
        return "neutral"
    if q2 == "Bad":
        return "negative"
    return "neutral"


def _tags_for(q2: str | None, q3: str | None, rng: random.Random) -> list[str]:
    tags: list[str] = []
    if q2 == "Excellent":
        tags.extend(rng.sample(POSITIVE_TAGS, k=rng.randint(1, 2)))
    elif q2 == "Good":
        tags.append(rng.choice(POSITIVE_TAGS + ["neutral"]))
    else:
        tags.extend(rng.sample(NEGATIVE_TAGS, k=rng.randint(1, 2)))
    if q3 == "Yes" and "resolved" not in tags:
        tags.append("resolved")
    return tags[:3]


def _issues_for(q2: str | None, q3: str | None, rng: random.Random) -> list[str]:
    if q2 != "Bad" and q3 != "No":
        return []
    pool = ["wait time", "communication", "billing", "booking", "staff attitude", "follow-up"]
    return rng.sample(pool, k=rng.randint(1, 2))


def _score_from_experience(q2: str | None, rng: random.Random) -> tuple[int, int]:
    if q2 == "Excellent":
        base = rng.randint(8, 10)
    elif q2 == "Good":
        base = rng.randint(6, 8)
    elif q2 == "Bad":
        base = rng.randint(3, 5)
    else:
        base = 6
    return base, base


def _wa_choice_answer(question: dict[str, Any], value: str) -> dict[str, Any]:
    return {
        "step_role": question["step_role"],
        "question": question["text"],
        "answer": value,
        "answer_text": value,
        "reply_type": "choice",
        "answer_type": "choice",
        "response_type": "text",
    }


def _wa_open_answer(
    question: dict[str, Any],
    *,
    mode: str,
    text: str,
    rng: random.Random,
    job_id: str | None = None,
) -> dict[str, Any]:
    if mode == "voice":
        status = _pick_weighted(rng, [("completed", 0.88), ("pending", 0.08), ("failed", 0.04)])
        entry = {
            "step_role": question["step_role"],
            "question": question["text"],
            "answer": text if status == "completed" else "",
            "answer_text": text if status == "completed" else "",
            "reply_type": "long_text",
            "answer_type": "open",
            "response_type": "voice_note",
            "answer_source": "voice_note",
            "transcription_status": status,
            "voice_note_job_id": job_id,
            "detected_language": "en",
        }
        if status == "failed":
            entry["transcription_error"] = "Demo: simulated transcription failure"
        return entry
    return {
        "step_role": question["step_role"],
        "question": question["text"],
        "answer": text,
        "answer_text": text,
        "reply_type": "long_text",
        "answer_type": "open",
        "response_type": "text",
        "answer_source": "text",
    }


def _build_wa_payload(
    plan: RespondentPlan,
    *,
    index: int,
    seed: int,
    started_at: datetime,
    completed_at: datetime | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rng = _rng_for(index, seed)
    answers: list[dict[str, Any]] = []
    voice_jobs: list[dict[str, Any]] = []

    if plan.answers_count >= 1 and plan.q1:
        answers.append(_wa_choice_answer(WA_QUESTIONS[0], plan.q1))
    if plan.answers_count >= 2 and plan.q2:
        answers.append(_wa_choice_answer(WA_QUESTIONS[1], plan.q2))
    if plan.answers_count >= 3 and plan.q3:
        answers.append(_wa_choice_answer(WA_QUESTIONS[2], plan.q3))
    if plan.answers_count >= 4 and plan.open_mode:
        if plan.open_mode == "voice":
            text = rng.choice(WA_VOICE_TRANSCRIPTS)
            job_id = str(uuid.uuid4())
            voice_jobs.append(
                {
                    "id": job_id,
                    "answer_text": text,
                    "transcription_status": "completed",
                    "answer_context": "final_feedback",
                    "step_index": 4,
                    "answer_index": len(answers),
                }
            )
            answers.append(_wa_open_answer(WA_QUESTIONS[3], mode="voice", text=text, rng=rng, job_id=job_id))
        else:
            answers.append(
                _wa_open_answer(WA_QUESTIONS[3], mode="text", text=rng.choice(WA_TEXT_FEEDBACK), rng=rng)
            )

    extracted = [{"question": a["question"], "answer": a.get("answer_text") or a.get("answer") or ""} for a in answers]
    sat, rec = _score_from_experience(plan.q2, rng)
    payload: dict[str, Any] = {
        "channel": "whatsapp",
        "terminal_status": plan.status,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat() if completed_at else None,
        "sentiment": plan.sentiment,
        "satisfaction_score": sat if plan.status == "completed" else None,
        "recommend_score": rec if plan.status == "completed" else None,
        "needs_follow_up": plan.needs_follow_up,
        "tags": plan.tags,
        "issues": plan.issues,
        "short_summary": _summary_for_plan(plan, channel="wa"),
        "wa_conversation": {
            "step": plan.answers_count,
            "total": 4,
            "answers": answers,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat() if completed_at and plan.status == "completed" else None,
        },
        "extracted_answers": extracted,
    }
    if plan.open_mode and answers:
        last = answers[-1]
        if last.get("answer_text"):
            payload["final_additional_feedback"] = last["answer_text"]
            payload["wa_conversation"]["final_additional_feedback"] = last["answer_text"]
    return payload, voice_jobs


def _build_call_transcript(plan: RespondentPlan, *, index: int, seed: int, answers: list[dict[str, Any]]) -> str:
    rng = _rng_for(index, seed + 17)
    lines = [
        "Agent: Hello, this is Alex calling from Demo Clinic — do you have two minutes for a short survey?",
        f"User: {'Yes, go ahead.' if plan.q1 == 'Yes' else 'I suppose so, make it quick.'}",
    ]
    for ans in answers[:3]:
        lines.append(f"Agent: {ans['question']}")
        lines.append(f"User: {ans['answer']}.")
    if len(answers) >= 4:
        lines.append(f"Agent: {answers[3]['question']}")
        open_text = answers[3].get("answer_text") or answers[3].get("answer") or ""
        if answers[3].get("response_type") == "voice_note":
            lines.append(f"User: [voice response transcribed] {open_text}")
        else:
            for chunk in _split_sentences(open_text, max_len=120):
                lines.append(f"User: {chunk}")
    lines.append("Agent: Thank you — that is everything from us today. Goodbye.")
    if plan.status != "completed":
        lines.append("Agent: It looks like we lost the line before the survey finished.")
    return "\n".join(lines)


def _split_sentences(text: str, *, max_len: int) -> list[str]:
    parts = [p.strip() for p in text.replace("—", ". ").split(". ") if p.strip()]
    if not parts:
        return [text[:max_len]]
    return parts


def _build_call_payload(
    plan: RespondentPlan,
    *,
    index: int,
    seed: int,
    started_at: datetime,
    completed_at: datetime | None,
) -> dict[str, Any]:
    rng = _rng_for(index, seed)
    extracted: list[dict[str, Any]] = []

    if plan.answers_count >= 1 and plan.q1:
        extracted.append({"question": CALL_QUESTIONS[0]["text"], "answer": plan.q1, "answer_type": "choice", "response_type": "text"})
    if plan.answers_count >= 2 and plan.q2:
        extracted.append({"question": CALL_QUESTIONS[1]["text"], "answer": plan.q2, "answer_type": "choice", "response_type": "text"})
    if plan.answers_count >= 3 and plan.q3:
        extracted.append({"question": CALL_QUESTIONS[2]["text"], "answer": plan.q3, "answer_type": "choice", "response_type": "text"})
    if plan.answers_count >= 4 and plan.open_mode:
        if plan.open_mode == "voice":
            text = rng.choice(CALL_VOICE_TRANSCRIPTS)
            extracted.append(
                {
                    "question": CALL_QUESTIONS[3]["text"],
                    "answer": text,
                    "answer_text": text,
                    "answer_type": "open",
                    "response_type": "voice_note",
                    "answer_source": "voice_note",
                    "transcription_status": "completed",
                }
            )
        else:
            text = rng.choice(CALL_TEXT_FEEDBACK)
            extracted.append(
                {
                    "question": CALL_QUESTIONS[3]["text"],
                    "answer": text,
                    "answer_text": text,
                    "answer_type": "open",
                    "response_type": "text",
                }
            )

    sat, rec = _score_from_experience(plan.q2, rng)
    transcript = _build_call_transcript(plan, index=index, seed=seed, answers=extracted) if extracted else ""

    return {
        "terminal_status": plan.status,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat() if completed_at else None,
        "duration_seconds": rng.randint(95, 420) if plan.status == "completed" else rng.randint(20, 90),
        "transcript": transcript,
        "needs_follow_up": plan.needs_follow_up,
        "analysis": {
            "short_summary": _summary_for_plan(plan, channel="call"),
            "sentiment": plan.sentiment,
            "satisfaction_score": sat,
            "recommend_score": rec,
            "extracted_answers": extracted,
            "issues": plan.issues,
            "tags": plan.tags,
            "needs_follow_up": plan.needs_follow_up,
            "completion_quality": "full" if plan.answers_count >= 4 else "partial",
        },
        "analysis_saved_at": datetime.utcnow().isoformat(),
        "analysis_version": ANALYSIS_VERSION,
        "short_summary": _summary_for_plan(plan, channel="call"),
        "sentiment": plan.sentiment,
        "satisfaction_score": sat,
        "recommend_score": rec,
        "extracted_answers": extracted,
        "issues": plan.issues,
        "tags": plan.tags,
    }


def _summary_for_plan(plan: RespondentPlan, *, channel: str) -> str:
    if plan.status != "completed":
        return f"{'WhatsApp' if channel == 'wa' else 'Call'} survey not fully completed."
    if plan.sentiment == "positive":
        return "Respondent reported a smooth experience and optional praise."
    if plan.sentiment == "negative":
        return "Respondent raised service issues" + (" with follow-up feedback." if plan.open_mode else ".")
    return "Mixed experience — some positives, some room to improve."


def _demo_wa_config() -> dict[str, Any]:
    return {
        "demo_survey_pack": DEMO_PACK_ID,
        "survey_channel": "whatsapp",
        "delivery": "whatsapp",
        "channels": ["whatsapp"],
        "contact_method": "WhatsApp",
        "goal": "Customer experience — WhatsApp demo",
        "organisation_name": "Demo Clinic",
        "survey_organiser_name": "Demo Team",
        "allow_final_additional_feedback": True,
        "script_approved": True,
    }


def _demo_call_config() -> dict[str, Any]:
    script_lines = ["INTRO", "Short AI phone survey demo.", "", "QUESTIONS"]
    for q in CALL_QUESTIONS:
        script_lines.append(f"{q['order']}. {q['text']}")
    script_lines.extend(["", "CLOSING", "Thank you for your time."])
    return {
        "demo_survey_pack": DEMO_PACK_ID,
        "survey_channel": "ai_call",
        "channels": ["call"],
        "contact_method": "AI phone call",
        "goal": "Customer experience — AI call demo",
        "organisation_name": "Demo Clinic",
        "survey_organiser_name": "Demo Team",
        "script_approved": True,
        "approved_script": "\n".join(script_lines),
        "system_prompt": "Run a polite outbound phone survey.",
    }


def _synthetic_contact(index: int, *, channel: str) -> dict[str, str]:
    prefix = "WA" if channel == "wa" else "Call"
    phone_base = 10_000 if channel == "wa" else 20_000
    return {
        "name": f"Demo {prefix} · Contact {index:03d}",
        "phone": f"+4477009{phone_base + index:05d}",
        "email": f"demo.{channel}.{index:03d}@example.invalid",
    }


def _approve_payment_flow(db, order: ServiceOrder) -> ServiceOrder:
    if order.quote_total_pence <= 0 or order.status == "draft":
        order = ServiceOrderService.quote_order(db, order)
    if order.payment_status != "approved":
        if order.payment_status != "pending_approval":
            order = ServiceOrderService.submit_cash_payment(db, order, note="Demo seed — synthetic")
        order = ServiceOrderService.admin_approve_payment(db, order, note="Demo seed — auto approved")
    return order


def _mark_order_finished(db, order: ServiceOrder, *, channel: str) -> ServiceOrder:
    now = datetime.utcnow()
    order.payment_status = "approved"
    order.payment_method = order.payment_method or "cash"
    order.status = "completed"
    order.scheduled_start_at = order.scheduled_start_at or (now - timedelta(days=5))
    order.scheduled_end_at = order.scheduled_end_at or (now - timedelta(days=1))
    order.started_at = order.started_at or (now - timedelta(days=3))
    order.completed_at = now - timedelta(hours=2)
    order.updated_at = now
    recipients = ServiceOrderService.get_recipients(db, order.id)
    completed = sum(1 for r in recipients if str(r.status or "").lower() == "completed")
    report = {
        "dispatch_at": now.isoformat(),
        "provider": "telnyx",
        "demo": True,
        "demo_survey_pack": DEMO_PACK_ID,
        "channel": channel,
        "total": len(recipients),
        "completed": completed,
        "sent": completed,
        "note": "Synthetic demo pack for reporting QA",
    }
    if channel == "ai_call":
        report["analysis"] = json.loads(order.report_json or "{}").get("analysis") if order.report_json else {}
    order.report_json = json.dumps(report, ensure_ascii=False)
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
        db.execute(delete(SurveyVoiceNoteJob).where(SurveyVoiceNoteJob.order_id == order.id))
        db.execute(delete(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id))
        db.delete(order)
        removed += 1
    if removed:
        db.commit()
    return removed


def _create_voice_jobs(
    db,
    *,
    org_id: str,
    order_id: str,
    recipient_id: str,
    jobs: list[dict[str, Any]],
    created_at: datetime,
) -> None:
    for offset, spec in enumerate(jobs):
        inbound_id = f"demo-inbound-{recipient_id}-{offset}"
        media_id = f"demo-media-{spec['id']}"
        db.add(
            SurveyVoiceNoteJob(
                id=spec["id"],
                org_id=org_id,
                order_id=order_id,
                recipient_id=recipient_id,
                answer_context=str(spec.get("answer_context") or "final_feedback"),
                step_index=int(spec.get("step_index") or 4),
                answer_index=spec.get("answer_index"),
                inbound_message_id=inbound_id,
                provider_media_id=media_id,
                media_url=f"https://demo.invalid/media/{media_id}",
                audio_file_path=f"data/survey_voice_notes/demo/{spec['id']}.ogg",
                audio_mime_type="audio/ogg",
                audio_file_size=12_000 + offset,
                answer_text=spec.get("answer_text"),
                answer_source="voice_note",
                transcription_status=str(spec.get("transcription_status") or "completed"),
                transcription_model="demo-seed",
                detected_language="en",
                transcribed_at=created_at + timedelta(minutes=2),
                processed_at=created_at + timedelta(minutes=2),
                created_at=created_at,
                updated_at=created_at,
            )
        )


def seed_channel_order(
    db,
    *,
    org_id: str,
    user_id: str,
    channel: str,
    count: int,
    seed: int,
) -> tuple[ServiceOrder, list[dict[str, Any]]]:
    now = datetime.utcnow()
    if channel == "wa":
        config = _demo_wa_config()
        title = f"Demo · WA mixed responses ({count})"
    else:
        config = _demo_call_config()
        title = f"Demo · AI Call mixed responses ({count})"

    order = ServiceOrderService.create_order(
        db,
        org_id=org_id,
        user_id=user_id,
        service_code="survey",
        title=title,
        config=config,
    )
    rows = [_synthetic_contact(i, channel=channel) for i in range(1, count + 1)]
    ServiceOrderService.replace_recipients(db, order, rows)
    db.refresh(order)
    order = _approve_payment_flow(db, order)

    recipients = ServiceOrderService.get_recipients(db, order.id)
    export_rows: list[dict[str, Any]] = []

    for recipient in recipients:
        idx = recipient.row_number
        plan = _plan_respondent(idx, seed, channel=channel)
        r = _rng_for(idx, seed)
        started = now - timedelta(days=r.randint(1, 10), hours=r.randint(1, 8))
        completed = started + timedelta(minutes=_rng_for(idx, seed).randint(3, 45)) if plan.status == "completed" else None

        if channel == "wa":
            payload, voice_jobs = _build_wa_payload(plan, index=idx, seed=seed, started_at=started, completed_at=completed)
            recipient.status = plan.status if plan.status != "failed" else "failed"
            if plan.status == "no_answer":
                recipient.status = "no_answer"
                payload = {"terminal_status": "no_answer"}
                voice_jobs = []
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
        export_rows.append(
            {
                "survey_id": order.id,
                "survey_type": channel,
                "survey_name": order.title,
                "contact_id": recipient.id,
                "contact_name": recipient.name,
                "phone": recipient.phone,
                "status": recipient.status,
                "started_at": started.isoformat(),
                "completed_at": completed.isoformat() if completed else None,
                "sentiment": plan.sentiment,
                "needs_follow_up": plan.needs_follow_up,
                "tags": plan.tags,
                "issues": plan.issues,
                "responses": json.loads(recipient.result_json or "{}"),
            }
        )

    db.commit()
    order = _mark_order_finished(db, order, channel=channel)
    return order, export_rows


def _validate_results(db, order: ServiceOrder, channel: str) -> dict[str, Any]:
    if channel == "wa":
        return build_whatsapp_survey_results_payload(db, order, include_respondents=True)
    return build_survey_results_payload(db, order, include_respondents=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed mixed WA + AI Call survey demo data (synthetic)")
    parser.add_argument("--email", default="user@user.com", help="Dashboard user email (org owner; must exist)")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help="Respondents per survey type")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="RNG seed for reproducible output")
    parser.add_argument("--clear", action="store_true", help="Remove previous demo pack orders first")
    parser.add_argument("--wa-only", action="store_true", help="Seed only WA Survey")
    parser.add_argument("--call-only", action="store_true", help="Seed only AI Call Survey")
    parser.add_argument("--export-json", metavar="PATH", help="Write flattened respondent export JSON")
    parser.add_argument("--skip-validate", action="store_true", help="Skip results payload validation")
    args = parser.parse_args()

    if args.wa_only and args.call_only:
        raise SystemExit("Use at most one of --wa-only / --call-only")

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

        if args.clear:
            removed = _clear_demo_orders(db, membership.org_id)
            print(f"Cleared {removed} previous demo order(s) (pack={DEMO_PACK_ID}).")

        channels: list[str] = []
        if not args.call_only:
            channels.append("wa")
        if not args.wa_only:
            channels.append("ai_call")

        all_export: list[dict[str, Any]] = []
        created: list[tuple[ServiceOrder, str]] = []

        for channel in channels:
            print(f"\nSeeding {channel} demo ({args.count} respondents, seed={args.seed})…")
            order, export_rows = seed_channel_order(
                db,
                org_id=membership.org_id,
                user_id=user.id,
                channel=channel,
                count=args.count,
                seed=args.seed,
            )
            created.append((order, channel))
            all_export.extend(export_rows)

            if not args.skip_validate:
                payload = _validate_results(db, order, channel)
                summary = payload.get("summary") or {}
                completed = int(summary.get("completed_count") or 0)
                print(f"  Order ID:     {order.id}")
                print(f"  Title:        {order.title}")
                print(f"  Completed:    {completed}/{args.count}")
                print(f"  Open feedback:{summary.get('open_feedback_count', summary.get('voice_feedback_count', '—'))}")
                print(f"  Aggregates:   {len(payload.get('aggregates') or [])} question blocks")

        if args.export_json:
            path = Path(args.export_json)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(all_export, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"\nExported {len(all_export)} respondent rows → {path}")

        print("\nDemo ready — open Dashboard → Surveys → Finished → View report")
        for order, channel in created:
            label = "WhatsApp" if channel == "wa" else "AI Call"
            print(f"  [{label}] {order.title}")
            print(f"           /surveys/results?orderId={order.id}")


if __name__ == "__main__":
    main()
