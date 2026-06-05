from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SurveyType(Base):
    """Reusable survey category managed under Platform Settings → WA Survey."""

    __tablename__ = "survey_types"
    __table_args__ = (UniqueConstraint("industry_id", "slug", name="uq_survey_types_industry_slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    industry_id: Mapped[str] = mapped_column(String(36), ForeignKey("industries.id"), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    default_length: Mapped[str] = mapped_column(String(16), nullable=False, default="standard")
    min_length: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    max_length: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    supports_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    system_template_kind: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
