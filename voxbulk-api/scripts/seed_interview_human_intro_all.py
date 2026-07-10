#!/usr/bin/env python3
"""Apply single human intro + recruiter behaviour to ALL interview agents in the DB.

Updates every AgentDefinition with supports_interview=True:
  - opening disclosure: name + company + role + recorded once + 10–15 min once (no AI wording)
  - call_workflow / interruption notes: do not re-introduce or restart full opener
  - conversation_style / system_prompt hints: human, emotional, reactive

Dialect-aware openings:
  - Egyptian (Jammal / EG) → Egyptian colloquial
  - Saudi Gulf (Sultan / SA) → Gulf colloquial
  - Other Arabic → MSA-leaning spoken Arabic (runtime still applies dialect rules)
  - English regional → British/regional English templates

Also re-runs the dedicated seed modules for regional EN + Sultan + Jammal so those
rows stay in sync with their canonical scripts.

Usage (from voxbulk-api, project venv):
  .venv/bin/python scripts/seed_interview_human_intro_all.py
  .venv/bin/python scripts/seed_interview_human_intro_all.py --dry-run
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.agent import AgentDefinition
from app.services.interview_agent_display_service import interview_agent_dialect_meta


def _agent_display_name(agent: AgentDefinition) -> str:
    return str(agent.voice_label or agent.name or "the recruiter").strip() or "the recruiter"


def _english_pack(agent: AgentDefinition) -> dict[str, str]:
    name = _agent_display_name(agent)
    return {
        "opening_disclosure_template": (
            f"Hello {{first_name}}, this is {name} calling from {{company_name}} "
            f"about the {{role}} role. This call is recorded for quality and assessment. "
            f"Do you have about 10 to 15 minutes now?"
        ),
        "call_workflow": (
            "Opening greeting and time ask were already spoken — do not re-introduce or re-ask for time.\n"
            "If the candidate agrees: proceed with CV questions then role questions in order.\n"
            "If busy or declines: offer a callback during working hours and end politely.\n"
            "Close with thanks and next-steps from the hiring team."
        ),
        "conversation_style": (
            "Human recruiter tone — warm, organised, not a script reader. "
            "Brief acknowledgements between questions. Do not restart the full introduction if interrupted."
        ),
        "interruption_behavior_notes": (
            "If interrupted mid-sentence, restate only the unfinished sentence — never restart the full introduction."
        ),
        "opt_out_policy_notes": "If remove me or stop calling, acknowledge, end call, never retry.",
    }


def _egyptian_pack(agent: AgentDefinition) -> dict[str, str]:
    name = _agent_display_name(agent)
    return {
        "opening_disclosure_template": (
            f"أهلاً {{first_name}}، معاك {name} باتصل من {{company_name}} بخصوص وظيفة {{role}}. "
            f"المكالمة مسجّلة للجودة. "
            f"عندك حوالي ١٠ إلى ١٥ دقيقة دلوقتي؟"
        ),
        "call_workflow": (
            "التحية والوقت اتسألوا بالفعل — متعدّش التعريف ولا سؤال الوقت.\n"
            "لو وافق: سيرة الأول، بعدين أسئلة الوظيفة.\n"
            "لو مشغول: رتّب معاد وانهِ بلباقة.\n"
            "اختتم: شكر + فريق التوظيف هيتواصل معاه."
        ),
        "conversation_style": (
            "نبرة ودودة وإنسانية — مكالمة توظيف حقيقية. جمل قصيرة. "
            "تكملات طبيعية: تمام، ماشي، أكيد، فهمت عليك. متطولش ومتعدّش المقدمة."
        ),
        "interruption_behavior_notes": (
            "لو قاطعك وسط جملة، أعد الجملة الناقصة بس بمصري بسيط — متعدّش المقدمة كاملة."
        ),
        "opt_out_policy_notes": "لو طلب ما يتصلوش تاني، اعتذر وانهِ ومتعاودش.",
    }


def _gulf_pack(agent: AgentDefinition) -> dict[str, str]:
    name = _agent_display_name(agent)
    return {
        "opening_disclosure_template": (
            f"السلام عليكم {{first_name}}، معك {name} أتصل من {{company_name}} بخصوص وظيفة {{role}}. "
            f"المكالمة مسجّلة للجودة. "
            f"عندك حوالي ١٠ إلى ١٥ دقيقة الحين؟"
        ),
        "call_workflow": (
            "التحية والوقت سُئلا بالفعل — لا تعِد التعريف ولا سؤال الوقت.\n"
            "إذا وافق المرشّح: سيرة أولاً، بعدين أسئلة الوظيفة.\n"
            "إذا مشغول: رتّب معاد وانهِ بلباقة.\n"
            "اختتم: شكر + فريق التوظيف يتواصل معه."
        ),
        "conversation_style": (
            "نبرة ودودة ومحترمة وإنسانية — مكالمة توظيف حقيقية. جمل قصيرة. "
            "تكملات طبيعية بين الأسئلة: تمام، زين، طيب، فهمت عليك. "
            "لا تطول في الكلام ولا تكرر نفس العبارة ولا تعِد المقدمة."
        ),
        "interruption_behavior_notes": (
            "إذا قاطعوا وسط جملة، أعد الجملة الناقصة فقط بخليجي بسيط — لا تعِد المقدمة كاملة."
        ),
        "opt_out_policy_notes": "إذا طلب ما يتصلون مرة ثانية، اعتذر وأنهِ ولا تعاود.",
    }


def _arabic_generic_pack(agent: AgentDefinition) -> dict[str, str]:
    name = _agent_display_name(agent)
    return {
        "opening_disclosure_template": (
            f"السلام عليكم {{first_name}}، معك {name} أتصل من {{company_name}} بخصوص وظيفة {{role}}. "
            f"المكالمة مسجّلة للجودة والتقييم. "
            f"هل لديك حوالي ١٠ إلى ١٥ دقيقة الآن؟"
        ),
        "call_workflow": (
            "التحية والوقت سُئلا بالفعل في بداية المكالمة — لا تعِد التعريف بنفسك ولا تعِد سؤال الوقت.\n"
            "انتظر تأكيد المرشّح: إذا وافق → ابدأ أسئلة السيرة ثم أسئلة الوظيفة بالترتيب.\n"
            "إذا مشغول أو رفض: اقترح معادًا خلال ساعات العمل وانهِ بلباقة.\n"
            "اختتم بالشكر وأخبره أن فريق التوظيف سيتواصل معه."
        ),
        "conversation_style": (
            "نبرة ودودة وإنسانية — مكالمة توظيف حقيقية. جمل قصيرة. "
            "ردود قصيرة بعد الإجابات. لا تعِد المقدمة."
        ),
        "interruption_behavior_notes": (
            "إذا قاطعك المرشّح وسط جملة، أعد الجملة الناقصة فقط — لا تعِد المقدمة كاملة."
        ),
        "opt_out_policy_notes": "إذا طلب الإزالة أو التوقف عن الاتصال، اعترف بلباقة وأنهِ ولا تتابع.",
    }


def _pack_for_agent(agent: AgentDefinition) -> dict[str, str]:
    dialect = str(interview_agent_dialect_meta(agent).get("dialect_code") or "").upper()
    if dialect == "EG":
        return _egyptian_pack(agent)
    if dialect == "SA":
        return _gulf_pack(agent)
    if dialect == "AR":
        return _arabic_generic_pack(agent)
    return _english_pack(agent)


def _scrub_ai_wording(text: str | None) -> str | None:
    raw = str(text or "")
    if not raw.strip():
        return text
    cleaned = raw
    cleaned = re.sub(r"\bthe AI assistant\b", "the recruiter", cleaned, flags=re.I)
    cleaned = re.sub(r"\ban AI assistant\b", "a recruiter", cleaned, flags=re.I)
    cleaned = re.sub(r"\bAI phone interviewer\b", "phone interviewer", cleaned, flags=re.I)
    cleaned = re.sub(r"\bAI assistant\b", "recruiter", cleaned, flags=re.I)
    cleaned = re.sub(r"\bchatbot\b", "recruiter", cleaned, flags=re.I)
    cleaned = cleaned.replace("المساعد الذكي", "موظف التوظيف").replace("مساعد ذكي", "موظف التوظيف")
    cleaned = cleaned.replace("ذكاء اصطناعي", "توظيف")
    return cleaned


def _apply_pack(agent: AgentDefinition, pack: dict[str, str], *, now: datetime) -> list[str]:
    changed: list[str] = []
    field_map = {
        "opening_disclosure_template": pack["opening_disclosure_template"],
        "call_workflow": pack["call_workflow"],
        "conversation_style": pack["conversation_style"],
        "interruption_behavior_notes": pack["interruption_behavior_notes"],
        "opt_out_policy_notes": pack["opt_out_policy_notes"],
    }
    for field, value in field_map.items():
        if str(getattr(agent, field, None) or "") != value:
            setattr(agent, field, value)
            changed.append(field)

    # Soft-scrub AI wording from system/base prompts without wiping custom content entirely.
    for field in ("system_prompt", "base_role", "service_interview_role", "description"):
        before = getattr(agent, field, None)
        after = _scrub_ai_wording(before)
        if after != before:
            setattr(agent, field, after)
            changed.append(f"{field}:scrub_ai")

    # Ensure disclosure flags for interview.
    if not agent.disclosure_for_interview:
        agent.disclosure_for_interview = True
        changed.append("disclosure_for_interview")
    if not agent.disclosure_mandatory:
        agent.disclosure_mandatory = True
        changed.append("disclosure_mandatory")

    # Append human-behavior reminder once if missing from system_prompt.
    prompt = str(agent.system_prompt or "")
    marker = "Never say you are an AI assistant"
    marker_ar = "لا تقل أبدًا إنك مساعد ذكي"
    dialect = str(interview_agent_dialect_meta(agent).get("dialect_code") or "").upper()
    if dialect in {"EG", "SA", "AR"}:
        if marker_ar not in prompt and "مساعد ذكي" not in prompt:
            agent.system_prompt = (
                (prompt + "\n" if prompt.strip() else "")
                + "لا تقل أبدًا إنك مساعد ذكي أو روبوت — قدّم نفسك باسمك فقط. "
                "التحية سُئلت بالفعل؛ لا تعِدها. كن إنسانيًا وردّ بردود قصيرة بعد الإجابات."
            ).strip()
            changed.append("system_prompt:human_note")
    else:
        if marker not in prompt:
            agent.system_prompt = (
                (prompt + "\n" if prompt.strip() else "")
                + "Never say you are an AI assistant, chatbot, or automated system — introduce yourself by name only. "
                "The opening greeting was already spoken; do not repeat it. "
                "Sound like a real recruiter: brief acknowledgements after answers."
            ).strip()
            changed.append("system_prompt:human_note")

    if changed:
        agent.updated_at = now
    return changed


def _run_canonical_seeds(*, dry_run: bool) -> None:
    if dry_run:
        print("DRY-RUN: skip canonical seed modules")
        return
    import runpy

    for rel in (
        "scripts/seed_interview_regional_agents.py",
        "scripts/seed_interview_ar_sultan_agent.py",
        "scripts/seed_interview_ar_jammal_agent.py",
    ):
        path = ROOT / rel
        if not path.is_file():
            print(f"WARN: missing {rel}")
            continue
        print(f"RUN: {rel}")
        runpy.run_path(str(path), run_name="__main__")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed human intro behaviour onto all interview agents")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    parser.add_argument(
        "--skip-canonical",
        action="store_true",
        help="Only patch DB rows; do not re-run regional/Sultan/Jammal seed modules",
    )
    args = parser.parse_args()

    if not args.skip_canonical:
        _run_canonical_seeds(dry_run=args.dry_run)

    Session = get_sessionmaker()
    db = Session()
    try:
        now = datetime.utcnow()
        agents = list(
            db.execute(
                select(AgentDefinition)
                .where(AgentDefinition.supports_interview.is_(True))
                .order_by(AgentDefinition.slug.asc())
            )
            .scalars()
            .all()
        )
        updated = 0
        for agent in agents:
            pack = _pack_for_agent(agent)
            dialect = interview_agent_dialect_meta(agent).get("dialect_code")
            changed = _apply_pack(agent, pack, now=now)
            if changed:
                updated += 1
                action = "WOULD UPDATE" if args.dry_run else "UPDATED"
                print(f"{action}: {agent.slug} dialect={dialect} fields={','.join(changed)}")
            else:
                print(f"OK: {agent.slug} dialect={dialect} (already current)")
            if not args.dry_run:
                db.add(agent)

        if args.dry_run:
            db.rollback()
            print(f"DRY-RUN complete: {updated}/{len(agents)} interview agents would change")
        else:
            db.commit()
            print(f"DONE: updated {updated}/{len(agents)} interview agents")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
