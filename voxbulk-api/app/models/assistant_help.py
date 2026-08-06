from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Date
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AssistantHelpChunk(Base):
    """RAG help chunk: builtin docs + FAQ + KB articles."""

    __tablename__ = "assistant_help_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    category_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    service_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    route_hints_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    helpful_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unhelpful_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("source_kind", "source_id", name="uq_help_chunk_source"),)


class AssistantConversation(Base):
    """Private per-user assistant conversation."""

    __tablename__ = "assistant_conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class AssistantMessage(Base):
    """Message in an assistant conversation."""

    __tablename__ = "assistant_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    sources_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class AssistantMessageFeedback(Base):
    """Thumbs up/down feedback on assistant messages."""

    __tablename__ = "assistant_message_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(36), ForeignKey("assistant_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    rating: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("message_id", "user_id", name="uq_message_feedback_user"),)


class AssistantFaqSuggestion(Base):
    """User-submitted FAQ suggestions from thumbs-down/general queries."""

    __tablename__ = "assistant_faq_suggestions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    sample_answer: Mapped[str] = mapped_column(Text, nullable=False)
    org_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class AssistantChatMetricDaily(Base):
    """Optional daily metrics for assistant chat usage."""

    __tablename__ = "assistant_chat_metrics_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day: Mapped[datetime] = mapped_column(Date, nullable=False, index=True, unique=True)
    questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kb_hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    general_ai: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    thumbs_up: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    thumbs_down: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms_sum: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
