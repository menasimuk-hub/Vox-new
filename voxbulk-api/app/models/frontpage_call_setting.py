from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FrontpageCallSetting(Base):
    __tablename__ = "frontpage_call_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    org_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_slug: Mapped[str | None] = mapped_column(String(120), nullable=True)
    stt_provider: Mapped[str] = mapped_column(String(40), nullable=False, default="deepgram")
    llm_provider: Mapped[str] = mapped_column(String(40), nullable=False, default="groq")
    tts_provider: Mapped[str] = mapped_column(String(40), nullable=False, default="cartesia")
    voice_provider: Mapped[str] = mapped_column(String(20), nullable=False, default="vapi")
    provider_agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    telnyx_greeting: Mapped[str | None] = mapped_column(Text, nullable=True)
    kb_file_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    kb_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
