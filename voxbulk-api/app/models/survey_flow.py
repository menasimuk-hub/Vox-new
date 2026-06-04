"""WA Survey flow definitions — nodes, edges, outcomes (P2)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SurveyFlowDefinition(Base):
    __tablename__ = "survey_flow_definitions"
    __table_args__ = (
        UniqueConstraint(
            "survey_type_id",
            "privacy_mode",
            "slug",
            "version",
            name="uq_survey_flow_def_type_privacy_slug_ver",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    survey_type_id: Mapped[str] = mapped_column(String(36), ForeignKey("survey_types.id"), nullable=False, index=True)
    privacy_mode: Mapped[str] = mapped_column(String(8), nullable=False, default="off", index=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    entry_node_key: Mapped[str] = mapped_column(String(64), nullable=False)
    fallback_outcome_key: Mapped[str] = mapped_column(String(64), nullable=False, default="neutral")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SurveyFlowNode(Base):
    __tablename__ = "survey_flow_nodes"
    __table_args__ = (
        UniqueConstraint("flow_id", "node_key", name="uq_survey_flow_nodes_flow_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    flow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("survey_flow_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_key: Mapped[str] = mapped_column(String(64), nullable=False)
    node_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    step_role: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    template_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("telnyx_whatsapp_templates.id"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_terminal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    outcome_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SurveyFlowEdge(Base):
    __tablename__ = "survey_flow_edges"
    __table_args__ = (
        UniqueConstraint("flow_id", "from_node_key", "priority", name="uq_survey_flow_edges_from_prio"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    flow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("survey_flow_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_node_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    to_node_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    rule_key: Mapped[str] = mapped_column(String(64), nullable=False)
    condition_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SurveyFlowOutcome(Base):
    __tablename__ = "survey_flow_outcomes"
    __table_args__ = (
        UniqueConstraint("flow_id", "outcome_key", name="uq_survey_flow_outcomes_flow_key"),
        UniqueConstraint("flow_id", "node_key", name="uq_survey_flow_outcomes_flow_node"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    flow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("survey_flow_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    outcome_key: Mapped[str] = mapped_column(String(64), nullable=False)
    node_key: Mapped[str] = mapped_column(String(64), nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False, default="send_text")
    template_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("telnyx_whatsapp_templates.id"), nullable=True
    )
    message_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
