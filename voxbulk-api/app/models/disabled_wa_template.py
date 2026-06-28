from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DisabledWaTemplate(Base):
    """Admin-managed list of WA template names to hide from user dashboards."""

    __tablename__ = "disabled_wa_templates"
    __table_args__ = (UniqueConstraint("normalized_name", name="uq_disabled_wa_tpl_normalized_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    normalized_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    raw_name: Mapped[str] = mapped_column(String(128), nullable=False)
    product_line: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    industry_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    survey_type_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    target_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="unresolved")
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    survey_type_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    survey_type_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    prior_flags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
