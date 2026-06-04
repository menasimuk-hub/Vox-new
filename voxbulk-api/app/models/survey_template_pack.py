"""OpenAI-generated WA survey template pack metadata."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SurveyTemplatePack(Base):
    __tablename__ = "survey_template_packs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    industry_id: Mapped[str] = mapped_column(String(36), ForeignKey("industries.id"), nullable=False, index=True)
    survey_type_id: Mapped[str] = mapped_column(String(36), ForeignKey("survey_types.id"), nullable=False, index=True)
    privacy_mode: Mapped[str] = mapped_column(String(8), nullable=False, default="off", index=True)
    template_count: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    service_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    theme_variant: Mapped[str | None] = mapped_column(String(128), nullable=True)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
