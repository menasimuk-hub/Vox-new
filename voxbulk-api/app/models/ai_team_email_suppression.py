from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AiTeamEmailSuppression(Base):
    """Global opt-out list for Apify / AI Team campaign outreach."""

    __tablename__ = "ai_team_email_suppressions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    unsubscribed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    source_recipient_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
