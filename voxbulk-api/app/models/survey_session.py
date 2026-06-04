"""WA Survey runtime sessions — structured answers and decision log (adaptive engine P1)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SurveySession(Base):
    __tablename__ = "survey_sessions"
    __table_args__ = (
        UniqueConstraint("recipient_id", name="uq_survey_sessions_recipient"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("service_orders.id"), nullable=False, index=True)
    recipient_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("service_order_recipients.id"), nullable=False, index=True
    )
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)

    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="whatsapp", index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    flow_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="linear")

    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    page_roles_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    flow_definition_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("survey_flow_definitions.id"), nullable=True, index=True
    )
    flow_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_node_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    question_visits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    survey_type_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("survey_types.id"), nullable=True)
    privacy_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    outcome_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome_delivery_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    picker_invocation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SurveySessionAnswer(Base):
    __tablename__ = "survey_session_answers"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_survey_session_answers_seq"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("survey_sessions.id"), nullable=False, index=True)

    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    step_role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    node_key: Mapped[str] = mapped_column(String(64), nullable=False)

    question_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    template_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    answered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SurveySessionDecision(Base):
    __tablename__ = "survey_session_decisions"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_survey_session_decisions_seq"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("survey_sessions.id"), nullable=False, index=True)

    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    rule_key: Mapped[str] = mapped_column(String(64), nullable=False)
    picker: Mapped[str] = mapped_column(String(32), nullable=False, default="deterministic")

    from_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    from_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    context_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    decided_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
