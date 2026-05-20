from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WhatsAppTemplate(Base):
    __tablename__ = "whatsapp_templates"
    __table_args__ = (UniqueConstraint("template_key", name="uq_whatsapp_templates_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
