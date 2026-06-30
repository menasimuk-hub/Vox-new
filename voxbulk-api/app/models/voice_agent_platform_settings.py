from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

DEFAULT_OPENING_DISCLOSURE = (
    "Hello, this is {agent_name}, the AI assistant calling from {company_name}. "
    "This call is recorded for quality and service purposes."
)

DEFAULT_OPENING_DISCLOSURE_AR = (
    "السلام عليكم، معك {agent_name}، المساعد الذكي من {company_name}. "
    "المكالمة مسجّلة للجودة والخدمة."
)


class VoiceAgentPlatformSettings(Base):
    __tablename__ = "voice_agent_platform_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    global_compliance_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    opening_disclosure_template: Mapped[str] = mapped_column(Text, nullable=False, default=DEFAULT_OPENING_DISCLOSURE)
    disclosure_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    disclosure_for_survey: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    disclosure_for_interview: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
