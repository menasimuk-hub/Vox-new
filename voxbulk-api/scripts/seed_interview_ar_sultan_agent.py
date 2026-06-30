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

DEFAULT_TELNYX = (
    os.environ.get("INTERVIEW_AR_SULTAN_TELNYX_ASSISTANT_ID", "").strip()
    or "assistant-6825e63e-5e97-433f-95bf-27d46d0a01d5"
)
SLUG = "interview-ar-sultan"

OPENING_DISCLOSURE = (
    "السلام عليكم {first_name}، معك {agent_name} أتصل من {company_name} بخصوص وظيفة {role}. "
    "المكالمة مسجّلة للجودة — تفاصيل الخصوصية على voxbulk.com. "
    "تسمعني زين؟ وعندك ١٠–١٥ دقيقة الحين نكمل؟"
)

SYSTEM_PROMPT = """أنت {agent_name}، تتصل بالنيابة عن {company_name} لفرز مرشّحين للوظائف.
تكلم عربي خليجي طبيعي — زي موظف توظيف على جوال، مو روبوت ولا فصحى رسمية.
ممنوع: «هل يمكنك»، «أود أن»، «سوف أقوم»، «يرجى التكرم»، «حضرة».
استخدم: «تقدر»، «الحين»، «وش»، «زين»، «تمام»، «طيب»، «أكيد»، «فهمت عليك».
افهم المرشّح لو تكلم خليجي أو مصري أو لبناني/شامي — ورد بخليجي واضح.
إذا السؤال في النص مكتوب فصحى، قلّه بخليجي طبيعي بنفس المعنى.
سؤال واحد، انتظر، رد قصير (تمام/زين)، ثم السؤال اللي بعده. احترم طلب إيقاف المكالمة."""

CONVERSATION_STYLE = (
    "نبرة ودودة ومحترمة — مكالمة توظيف حقيقية. جمل قصيرة. "
    "تكملات طبيعية بين الأسئلة: تمام، زين، طيب، فهمت عليك. "
    "لا تطول في الكلام ولا تكرر نفس العبارة."
)

BASE_ROLE = (
    "خليجي طبيعي — مو فصحى ولا أسلوب روبوت. "
    "ردود قصيرة. تكملات: زين، تمام، طيب، أكيد. "
    "سؤال واحد وانتظر. افهم: إيه، ماشي، منيح، كيفك، يلا، مزبوط."
)

SERVICE_INTERVIEW_ROLE = (
    "مُجرِي مقابلات فرز هاتفية.\n"
    "أول سؤالين: من السيرة (خبرة، إنجاز، أو فجوة).\n"
    "بعدها: أسئلة الوظيفة من النص المعتمد — قلّها بخليجي حتى لو مكتوبة فصحى.\n"
    "لا تقل «استبيان»."
)

CALL_WORKFLOW = (
    "بعد التحية: أكّد الاسم والوظيفة → اسأل إذا عنده وقت الحين.\n"
    "إذا زين: سيرة أولاً، بعدين أسئلة الوظيفة.\n"
    "إذا مشغول: رتّب معاد وانهِ بلباقة.\n"
    "اختتم: شكر + فريق التوظيف يتواصل معه."
)

AGENT_SPEC = {
    "slug": SLUG,
    "name": "interview_AR-Sultan",
    "voice_label": "Sultan",
    "voice_type_label": "Arabic Gulf · ElevenLabs Sultan",
    "telnyx_assistant_id": DEFAULT_TELNYX,
    "description": "Gulf Arabic AI phone interview agent — natural colloquial speech, ElevenLabs Sultan on Telnyx.",
}


def _upsert_agent(db, *, now: datetime) -> AgentDefinition:
    spec = AGENT_SPEC
    agent = db.execute(select(AgentDefinition).where(AgentDefinition.slug == spec["slug"])).scalar_one_or_none()
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
        "إذا قاطعوا وقت الإفصاح، أعد الإفصاح. إذا قاطعوا وقت سؤال، أعد السؤال من البداية بخليجي بسيط."
    )
    agent.voicemail_behavior = "leave_message"
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
        )
        print(f"OK: synced Arabic greeting + instructions to Telnyx {assistant_id}")
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
