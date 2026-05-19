from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgentKnowledgeFile(Base):
    __tablename__ = "agent_knowledge_files"
    __table_args__ = (UniqueConstraint("agent_id", "knowledge_base_file_id", name="uq_agent_kb_file"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    knowledge_base_file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_base_files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
