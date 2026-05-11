from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EmailTemplate(Base):
    """
    Editable transactional / notification email templates (platform-wide).
    """

    __tablename__ = "email_templates"
    __table_args__ = (UniqueConstraint("template_key", name="uq_email_templates_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
