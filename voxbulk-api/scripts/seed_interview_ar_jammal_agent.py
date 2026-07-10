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

DEFAULT_TELNYX = os.environ.get("INTERVIEW_AR_JAMMAL_TELNYX_ASSISTANT_ID", "").strip()
SLUG = "interview-ar-jammal"

OPENING_DISCLOSURE = (
    "أهلاً {first_name}، معاك {agent_name} باتصل من {company_name} بخصوص وظيفة {role}. "
    "المكالمة مسجّلة للجودة. "
    "عندك حوالي ١٠ إلى ١٥ دقيقة دلوقتي؟"
)

SYSTEM_PROMPT = """أنت {agent_name}، بتتصل بالنيابة عن {company_name} لفرز مرشّحين.
تكلم مصري طبيعي — زي موظف توظيف على التليفون، مش روبوت ولا فصحى.
ممنوع تقول إنك مساعد ذكي أو روبوت أو نظام آلي — قدّم نفسك باسمك بس.
افهم لو المرشّح تكلم خليجي أو شامي أو مصري — ورد بمصري واضح ومحترم.
التحية والوقت اتسألوا في أول المكالمة — متعدّش التعريف بنفسك ومتعدّش سؤال الوقت.
سؤال واحد، استنى، رد قصير عاطفي طبيعي (تمام/ماشي/فهمت عليك)، بعدين السؤال اللي بعده."""

CONVERSATION_STYLE = (
    "نبرة ودودة وإنسانية — مكالمة توظيف حقيقية. جمل قصيرة. "
    "تكملات طبيعية: تمام، ماشي، أكيد، فهمت عليك. متطولش ومتعدّش المقدمة."
)

BASE_ROLE = (
    "مصري طبيعي — مش فصحى ولا روبوت. "
    "ردود قصيرة. سؤال واحد واستنى."
)

SERVICE_INTERVIEW_ROLE = (
    "مُجرِي مقابلات فرز هاتفية.\n"
    "أول سؤالين من السيرة، بعدين أسئلة الوظيفة بمصري حتى لو مكتوبة فصحى.\n"
    "متقلش استبيان. متعدّش التحية."
)

CALL_WORKFLOW = (
    "التحية والوقت اتسألوا بالفعل — متعدّش التعريف ولا سؤال الوقت.\n"
    "لو وافق: سيرة الأول، بعدين أسئلة الوظيفة.\n"
    "لو مشغول: رتّب معاد وانهِ بلباقة.\n"
    "اختتم: شكر + فريق التوظيف هيتواصل معاه."
)

AGENT_SPEC = {
    "slug": SLUG,
    "name": "interview_AR-Jammal",
    "voice_label": "Jammal",
    "voice_type_label": "🇪🇬 Egyptian Arabic",
    "telnyx_assistant_id": DEFAULT_TELNYX,
    "description": "Egyptian Arabic AI phone interview agent.",
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
    telnyx_id = str(spec.get("telnyx_assistant_id") or "").strip()
    if telnyx_id:
        agent.telnyx_assistant_id = telnyx_id
    agent.opening_disclosure_template = OPENING_DISCLOSURE
    agent.supports_interview = True
    agent.supports_survey = False
    agent.disclosure_for_interview = True
    agent.disclosure_mandatory = True
    agent.interruption_behavior_notes = (
        "لو قاطعك وسط جملة، أعد الجملة الناقصة بس بمصري بسيط — متعدّش المقدمة كاملة."
    )
    agent.is_active = True
    return agent


def main() -> None:
    Session = get_sessionmaker()
    db = Session()
    try:
        now = datetime.utcnow()
        agent = _upsert_agent(db, now=now)
        db.commit()
        db.refresh(agent)
        print(f"OK: interview agent id={agent.id} slug={agent.slug} name={agent.name}")
        print(f"     telnyx_assistant_id={agent.telnyx_assistant_id or '(set INTERVIEW_AR_JAMMAL_TELNYX_ASSISTANT_ID)'}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
