#!/usr/bin/env python3
"""Seed or update Egyptian Arabic interview agent «Jammal» (optional Telnyx assistant).

Usage:
  INTERVIEW_AR_JAMMAL_TELNYX_ASSISTANT_ID=assistant-... python3 scripts/seed_interview_ar_jammal_agent.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.agent import AgentDefinition
from app.services.voice_agent_runtime import ARABIC_EGYPTIAN_INTERVIEW_CALL_WORKFLOW

DEFAULT_TELNYX = os.environ.get("INTERVIEW_AR_JAMMAL_TELNYX_ASSISTANT_ID", "").strip()
SLUG = "interview-ar-jammal"

# Start with identity check only — intro / duration / recording live in the canonical workflow.
OPENING_DISCLOSURE = "مرحباً، ممكن اتكلم مع {first_name}؟"

SYSTEM_PROMPT = """أنت {agent_name}، بتتصل بالنيابة عن {company_name} لمقابلة مرشّحين.
اسمك المنطوق حرفيًا: جمال — لما تعرّف نفسك قل «معك جمال من …». ممنوع تنطقه «جمل» أو «جامال» أو أي لفظ غلط.
تكلم مصري مهني واضح ومرتّب — ممثل توظيف محترف، مش روبوت ومش فصحى جامدة ومش كلام أصحاب.
نبرة هادئة وثابتة، سرعة طبيعية، مخارج حروف واضحة. متستعجلش ومش تغمغم.
ممنوع اختراع أوصاف زي «مقابلة فرد» أو «فرز» — قل: أتصل بخصوص مقابلة {role}.
اتبع سير المكالمة الكنسي حرفيًا: هوية → تعريف+وقت → تسجيل (إلزامي) → أسئلة → إغلاق.
لو الوقت مش مناسب: جملة رابط الإيميل فقط وأنهِ — متطلبش معاد شفهي.
الرد الآلي: متقولش حاجة وانهِ فورًا.
سؤال واحد، استنى بهدوء. نوّع ردود قصيرة مهنية (تمام / مفهوم / شكراً) مع استماع ذكي.
اختتم: شكر + الفريق هيراجع خلال الإطار الزمني + مع السلامة."""

CONVERSATION_STYLE = (
    "نبرة مهنية هادئة وواضحة — ممثل شركة محترف. جمل قصيرة مرتّبة. مصري واضح مش فصحى جامدة. "
    "اسمك جمال فقط (مش جمل). سرعة طبيعية مش بطيئة ومش مستعجلة. "
    "اتبع السير الكنسي. اسمع بذكاء: وضّح / تابع / اذكر تفصيلة. متقاطعش المرشّح."
)

BASE_ROLE = (
    "مصري مهني — مش فصحى ولا روبوت. اتبع السير الكنسي. "
    "سؤال واحد واستنى. اسمع بذكاء — متقولش تمام لوحدها وتنقل."
)

SERVICE_INTERVIEW_ROLE = (
    "مُجرِي مقابلات هاتفية بمصري مهني.\n"
    "بعد تأكيد الهوية والوقت والإفصاح عن التسجيل: أسئلة النص بالترتيب.\n"
    "استمع بذكاء: وضّح / تابع / اذكر تفصيلة.\n"
    "متقلش استبيان. متعدّش سؤال الهوية. متخترعش «مقابلة فرد»."
)

CALL_WORKFLOW = ARABIC_EGYPTIAN_INTERVIEW_CALL_WORKFLOW

AGENT_SPEC = {
    "slug": SLUG,
    "name": "interview_AR-Jammal",
    "voice_label": "Jammal",
    "voice_type_label": "🇪🇬 Egyptian Arabic",
    "telnyx_assistant_id": DEFAULT_TELNYX,
    "description": "Egyptian Arabic AI phone interview agent — natural Masri, never Fusha on the call.",
}


def _upsert_agent(db, *, now: datetime) -> AgentDefinition:
    from sqlalchemy import or_, select

    spec = AGENT_SPEC
    agent = db.execute(select(AgentDefinition).where(AgentDefinition.slug == spec["slug"])).scalar_one_or_none()
    if agent is None:
        agent = db.execute(
            select(AgentDefinition)
            .where(
                AgentDefinition.supports_interview.is_(True),
                or_(
                    AgentDefinition.name.ilike("%jammal%"),
                    AgentDefinition.name.ilike("%jamal%"),
                    AgentDefinition.voice_label.ilike("%jammal%"),
                    AgentDefinition.voice_label.ilike("%jamal%"),
                ),
            )
            .limit(1)
        ).scalar_one_or_none()
    if agent is None:
        agent = AgentDefinition(
            name=spec["name"],
            slug=spec["slug"],
            description=spec["description"],
            system_prompt=SYSTEM_PROMPT,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(agent)
    else:
        agent.updated_at = now

    agent.name = spec["name"]
    agent.slug = spec["slug"]
    agent.description = spec["description"]
    agent.system_prompt = SYSTEM_PROMPT
    agent.conversation_style = CONVERSATION_STYLE
    agent.call_workflow = CALL_WORKFLOW
    agent.base_role = BASE_ROLE
    agent.service_interview_role = SERVICE_INTERVIEW_ROLE
    agent.voice_label = spec["voice_label"]
    agent.voice_type_label = spec["voice_type_label"]
    agent.accent_region = "EG"
    agent.gender = "male"
    telnyx_id = str(spec.get("telnyx_assistant_id") or "").strip()
    if telnyx_id:
        agent.telnyx_assistant_id = telnyx_id
    agent.opening_disclosure_template = OPENING_DISCLOSURE
    agent.supports_interview = True
    agent.supports_survey = False
    agent.disclosure_for_interview = True
    agent.disclosure_mandatory = True
    agent.interruption_behavior_notes = (
        "متقاطعش المرشّح وهو بيرد. لو قاطعك وسط جملة، أعد الجملة الناقصة بس بمصري بسيط — متعدّش المقدمة كاملة."
    )
    agent.voicemail_behavior = "hang_up"
    agent.is_active = True
    return agent


def _maybe_sync_telnyx(db, agent: AgentDefinition) -> None:
    if os.environ.get("INTERVIEW_AR_JAMMAL_SYNC_TELNYX", "1").strip().lower() in {"0", "false", "no"}:
        print("SKIP: Telnyx sync disabled (INTERVIEW_AR_JAMMAL_SYNC_TELNYX=0)")
        return
    assistant_id = str(agent.telnyx_assistant_id or "").strip()
    if not assistant_id:
        print("WARN: no telnyx_assistant_id — skip sync")
        return
    from app.services.telnyx_assistant_service import sync_telnyx_assistant_instructions

    sample_greeting = (
        OPENING_DISCLOSURE.replace("{first_name}", "أحمد")
        .replace("{agent_name}", "جمال")
        .replace("{company_name}", "VoxBulk")
        .replace("{role}", "مساعد استقبال")
    )
    try:
        sync_telnyx_assistant_instructions(
            db,
            assistant_id,
            SYSTEM_PROMPT.replace("{agent_name}", "جمال").replace("{company_name}", "VoxBulk"),
            greeting=sample_greeting,
            sync_greeting=True,
            enable_web_calls=True,
            verify_live=False,
            language="ar",
            apply_human_pacing=True,
        )
        print(f"OK: synced Egyptian greeting + instructions + human pacing to Telnyx {assistant_id}")
    except Exception as exc:
        print(f"WARN: Telnyx sync failed ({exc}) — agent saved in DB; assign/sync from Admin if needed.")


def main() -> None:
    Session = get_sessionmaker()
    db = Session()
    try:
        now = datetime.utcnow()
        agent = _upsert_agent(db, now=now)
        db.commit()
        db.refresh(agent)
        print(f"OK: interview agent id={agent.id} slug={agent.slug} name={agent.name}")
        print(f"     opening={agent.opening_disclosure_template}")
        print(f"     telnyx_assistant_id={agent.telnyx_assistant_id or '(set INTERVIEW_AR_JAMMAL_TELNYX_ASSISTANT_ID)'}")
        _maybe_sync_telnyx(db, agent)
    finally:
        db.close()


if __name__ == "__main__":
    main()
