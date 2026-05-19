from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgentServiceAssignment(Base):
    """Maps one agent to a platform service for a specific organisation (client)."""

    __tablename__ = "agent_service_assignments"
    __table_args__ = (UniqueConstraint("org_id", "service_key", name="uq_agent_service_org_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    service_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_definitions.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
