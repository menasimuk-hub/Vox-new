"""Many-to-many mapping between survey types and shared WhatsApp templates."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SurveyTypeTemplate(Base):
    __tablename__ = "survey_type_templates"
    __table_args__ = (
        UniqueConstraint("survey_type_id", "template_id", name="uq_survey_type_template_map"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    survey_type_id: Mapped[str] = mapped_column(String(36), ForeignKey("survey_types.id"), nullable=False, index=True)
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("telnyx_whatsapp_templates.id"), nullable=False, index=True)
    usable_as_standard: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    usable_as_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_default_standard: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_default_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    privacy_mode: Mapped[str] = mapped_column(String(8), nullable=False, default="off", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
