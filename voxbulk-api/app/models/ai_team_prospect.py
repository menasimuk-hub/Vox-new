from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AiTeamProspect(Base):
    __tablename__ = "ai_team_prospects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    apollo_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    first_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    last_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    job_title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    company_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    sector: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    country_code: Mapped[str] = mapped_column(String(8), nullable=False, default="GB")

    match_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="new", index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="apollo")

    promo_offer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("promo_offers.id"), nullable=True, index=True)

    draft_subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    draft_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    drafted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    resend_email_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    emails_sent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    followups_sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    profile_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
