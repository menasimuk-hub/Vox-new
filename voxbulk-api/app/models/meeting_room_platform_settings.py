from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.constants.meeting_room_languages import DEFAULT_MEETING_ROOM_LANGUAGE


class MeetingRoomPlatformSettings(Base):
    __tablename__ = "meeting_room_platform_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_definitions.id"), nullable=True, index=True
    )
    language_code: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DEFAULT_MEETING_ROOM_LANGUAGE
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
