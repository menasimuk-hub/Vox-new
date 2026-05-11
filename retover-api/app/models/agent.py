from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgentDefinition(Base):
    __tablename__ = "agent_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    business_type: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    category_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("categories.id"), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    conversation_style: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    default_voice: Mapped[str | None] = mapped_column(String(120), nullable=True)
    use_azure_tts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    use_azure_stt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_booking_tool: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_lookup_tool: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_reschedule_tool: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_cancel_tool: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_template: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class AgentAssignment(Base):
    __tablename__ = "agent_assignments"
    __table_args__ = (
        UniqueConstraint("org_id", name="uq_agent_assignment_org"),
        UniqueConstraint("category_id", name="uq_agent_assignment_category"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_definitions.id"), nullable=False, index=True)
    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=True, index=True)
    category_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("categories.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
