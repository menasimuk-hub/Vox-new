#!/usr/bin/env python3
"""Seed or update Gulf Arabic interview agent «Sultan» (ElevenLabs voice on Telnyx).

Usage (from voxbulk-api, project venv):
  .venv/bin/python scripts/seed_interview_ar_sultan_agent.py

Optional env:
  INTERVIEW_AR_SULTAN_TELNYX_ASSISTANT_ID=assistant-6825e63e-5e97-433f-95bf-27d46d0a01d5
  INTERVIEW_AR_SULTAN_SYNC_TELNYX=1   # push greeting + base prompt to Telnyx (needs API key in DB)
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
from app.services.voice_agent_runtime import ARABIC_INTERVIEW_CALL_WORKFLOW

DEFAULT_TELNYX = (
    os.environ.get("INTERVIEW_AR_SULTAN_TELNYX_ASSISTANT_ID", "").strip()
    or "assistant-6825e63e-5e97-433f-95bf-27d46d0a01d5"
)
SLUG = "interview-ar-sultan"

OPENING_DISCLOSURE = "مرحباً، ممكن اتكلم مع {first_name}؟"

SYSTEM_PROMPT = """أنت {agent_name}، تتصل بالنيابة عن {company_name} لمقابلة مرشّحين للوظائف.
تكلم عربي خليجي مهني دافئ — ممثل شركة، مو روبوت ولا فصحى رسمية ولا كلام أصحاب.
ممنوع اختراع أوصاف مثل «مقابلة فرد» أو «فرز» — قل: أتصل بخصوص مقابلة {role}.
اتبع سير المكالمة الكنسي حرفيًا: هوية → تعريف+وقت → تسجيل (إلزامي) → أسئلة → إغلاق.
إذا الوقت غير مناسب: جملة رابط الإيميل فقط وأنهِ — لا تطلب معاد شفهي.
الرد الآلي: لا تقول شيء وأنهِ فورًا.
سؤال واحد، انتظر. نوّع ردود قصيرة (تمام / مفهوم / شكراً) مع استماع ذكي.
اختتم: شكر + الفريق بيراجع خلال الإطار الزمني + مع السلامة."""

CONVERSATION_STYLE = (
    "نبرة مهنية ودافئة — مكالمة ممثل شركة. جمل قصيرة. "
    "اتبع السير الكنسي. اسمع بذكاء: وضّح / تابع / اذكر تفصيلة. لا تقاطع المرشّح."
)

BASE_ROLE = (
    "خليجي مهني — مو فصحى ولا روبوت. اتبع السير الكنسي. "
    "سؤال واحد وانتظر. اسمع بذكاء — لا تقل تمام لوحدها وتنتقل."
)

SERVICE_INTERVIEW_ROLE = (
    "مُجرِي مقابلات هاتفية.\n"
    "بعد تأكيد الهوية والوقت والإفصاح عن التسجيل: أسئلة النص بالترتيب.\n"
    "استمع بذكاء: وضّح / تابع / اذكر تفصيلة.\n"
    "لا تقل «استبيان». لا تعِد سؤال الهوية. لا تخترع «مقابلة فرد»."
)

CALL_WORKFLOW = ARABIC_INTERVIEW_CALL_WORKFLOW

AGENT_SPEC = {
    "slug": SLUG,
    "name": "interview_AR-Sultan",
    "voice_label": "Sultan",
    "voice_type_label": "🇸🇦 Saudi Gulf · ElevenLabs Sultan",
    "telnyx_assistant_id": DEFAULT_TELNYX,
    "description": "Gulf Arabic AI phone interview agent — natural colloquial speech, ElevenLabs Sultan on Telnyx.",
}


def _find_interview_agent(db, *, slug: str, name_patterns: tuple[str, ...]) -> AgentDefinition | None:
    from sqlalchemy import or_, select

    agent = db.execute(select(AgentDefinition).where(AgentDefinition.slug == slug)).scalar_one_or_none()
    if agent is not None:
        return agent
    clauses = []
    for pat in name_patterns:
        like = f"%{pat}%"
        clauses.extend(
            [
                AgentDefinition.name.ilike(like),
                AgentDefinition.voice_label.ilike(like),
            ]
        )
    return db.execute(
        select(AgentDefinition)
        .where(
            AgentDefinition.supports_interview.is_(True),
            or_(*clauses),
        )
        .order_by(AgentDefinition.updated_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _upsert_agent(db, *, now: datetime) -> AgentDefinition:
    spec = AGENT_SPEC
    agent = _find_interview_agent(db, slug=spec["slug"], name_patterns=("sultan", "interview_ar-sultan"))
    if agent is None:
        agent = AgentDefinition(
            name=spec["name"],
            slug=spec["slug"],
            description=spec["description"],
            system_prompt=SYSTEM_PROMPT,
            call_workflow=CALL_WORKFLOW,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(agent)
    else:
        agent.updated_at = now

    agent.name = spec["name"]
    agent.description = spec["description"]
    agent.system_prompt = SYSTEM_PROMPT
    agent.conversation_style = CONVERSATION_STYLE
    agent.call_workflow = CALL_WORKFLOW
    agent.voice_label = spec["voice_label"]
    agent.voice_type_label = spec["voice_type_label"]
    telnyx_id = str(spec.get("telnyx_assistant_id") or "").strip()
    if telnyx_id:
        agent.telnyx_assistant_id = telnyx_id
    agent.base_role = BASE_ROLE
    agent.service_interview_role = SERVICE_INTERVIEW_ROLE
    agent.service_survey_role = None
    agent.opening_disclosure_template = OPENING_DISCLOSURE
    agent.supports_survey = False
    agent.supports_interview = True
    agent.supports_lead_sales = False
    agent.supports_appointment = False
    agent.is_default_interview = False
    agent.disclosure_for_survey = False
    agent.disclosure_for_interview = True
    agent.disclosure_mandatory = True
    agent.retry_policy_notes = "محاولة ثانية بعد ساعتين إذا ما رد أو مشغول."
    agent.interruption_behavior_notes = (
        "إذا قاطعوا وسط جملة، أعد الجملة الناقصة فقط بخليجي بسيط — لا تعِد المقدمة كاملة."
    )
    agent.voicemail_behavior = "hang_up"
    agent.accent_region = "SA"
    agent.opt_out_policy_notes = "إذا طلب ما يتصلون مرة ثانية، اعتذر وأنهِ ولا تعاود."
    agent.is_active = True
    return agent


def _maybe_sync_telnyx(db, agent: AgentDefinition) -> None:
    if os.environ.get("INTERVIEW_AR_SULTAN_SYNC_TELNYX", "1").strip().lower() in {"0", "false", "no"}:
        print("SKIP: Telnyx sync disabled (INTERVIEW_AR_SULTAN_SYNC_TELNYX=0)")
        return
    assistant_id = str(agent.telnyx_assistant_id or "").strip()
    if not assistant_id:
        print("WARN: no telnyx_assistant_id — skip sync")
        return
    from app.services.telnyx_assistant_service import sync_telnyx_assistant_instructions

    sample_greeting = OPENING_DISCLOSURE.replace("{first_name}", "أحمد").replace("{agent_name}", "سلطان").replace(
        "{company_name}", "VoxBulk"
    ).replace("{role}", "مساعد استقبال")
    try:
        sync_telnyx_assistant_instructions(
            db,
            assistant_id,
            SYSTEM_PROMPT.replace("{agent_name}", "سلطان").replace("{company_name}", "VoxBulk"),
            greeting=sample_greeting,
            sync_greeting=True,
            enable_web_calls=True,
            verify_live=False,
            language="ar",
            apply_human_pacing=True,
        )
        print(f"OK: synced Arabic greeting + instructions + human pacing to Telnyx {assistant_id}")
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
        print(f"     telnyx_assistant_id={agent.telnyx_assistant_id}")
        print(f"     voice_label={agent.voice_label}")
        _maybe_sync_telnyx(db, agent)
        print("\nTest in Admin -> Agents -> interview_AR-Sultan -> Test WebRTC call")
        print("Or pick Sultan when creating an interview campaign in the dashboard.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
