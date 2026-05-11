from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent import AgentDefinition
from app.services.agents.prompts import (
    BRITISH_CLINIC_ASSISTANT_PROMPT,
    DEFAULT_AGENT_SLUG,
    DEFAULT_CONVERSATION_STYLE,
)


class AgentRegistry:
    @staticmethod
    def ensure_default_agents(db: Session) -> AgentDefinition:
        existing = db.execute(select(AgentDefinition).where(AgentDefinition.slug == DEFAULT_AGENT_SLUG)).scalar_one_or_none()
        if existing is not None:
            return existing
        now = datetime.utcnow()
        agent = AgentDefinition(
            name="British Clinic Assistant",
            slug=DEFAULT_AGENT_SLUG,
            business_type="dental_clinic",
            description="Default VOXBULK voice assistant for dental appointment recovery and rebooking conversations.",
            system_prompt=BRITISH_CLINIC_ASSISTANT_PROMPT,
            conversation_style=DEFAULT_CONVERSATION_STYLE,
            default_model="gpt-realtime-1.5",
            default_voice="en-GB-AbbiNeural",
            use_azure_tts=True,
            use_azure_stt=True,
            allow_lookup_tool=True,
            allow_booking_tool=False,
            allow_reschedule_tool=False,
            allow_cancel_tool=False,
            is_active=True,
            is_template=True,
            created_at=now,
            updated_at=now,
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)
        return agent
