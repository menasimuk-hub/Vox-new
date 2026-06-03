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
    call_workflow: Mapped[str | None] = mapped_column(Text, nullable=True)
    kb_context: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    voice_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    voice_type_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telnyx_assistant_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    base_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_survey_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_interview_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_lead_sales_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    supports_survey: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_interview: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_lead_sales: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_default_survey: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_default_interview: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_default_lead_sales: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    opening_disclosure_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    disclosure_for_survey: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    disclosure_for_interview: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    disclosure_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    retry_policy_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    interruption_behavior_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    voicemail_behavior: Mapped[str | None] = mapped_column(String(32), nullable=True)
    missed_call_email_template_interview: Mapped[str | None] = mapped_column(String(64), nullable=True)
    missed_call_email_template_survey: Mapped[str | None] = mapped_column(String(64), nullable=True)
    missed_call_followup_notes_interview: Mapped[str | None] = mapped_column(Text, nullable=True)
    opt_out_policy_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
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
