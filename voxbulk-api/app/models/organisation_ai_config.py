from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OrganisationAIIdentity(Base):
    __tablename__ = "organisation_ai_identities"
    __table_args__ = (UniqueConstraint("org_id", name="uq_organisation_ai_identities_org"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    assistant_name: Mapped[str] = mapped_column(String(120), nullable=False, default="VOXBULK Assistant")
    organisation_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tone: Mapped[str] = mapped_column(String(40), nullable=False, default="professional")
    humor_level: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    languages_json: Mapped[str] = mapped_column(Text, nullable=False, default='["en-GB"]')
    terminology_label: Mapped[str] = mapped_column(String(40), nullable=False, default="patient")
    disclose_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class OrganisationComplianceConfig(Base):
    __tablename__ = "organisation_compliance_configs"
    __table_args__ = (UniqueConstraint("org_id", name="uq_organisation_compliance_configs_org"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    outbound_call_windows_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    whatsapp_windows_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    weekend_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ai_disclosure_wording: Mapped[str | None] = mapped_column(Text, nullable=True)
    opt_out_wording: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalation_destination: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_preference_rules_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    privacy_notice_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dpo_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    opt_out_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    lawful_basis_default: Mapped[str | None] = mapped_column(String(32), nullable=True)
    special_category_data_present_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    article9_condition_default: Mapped[str | None] = mapped_column(String(64), nullable=True)
    privacy_intro_text_default: Mapped[str | None] = mapped_column(Text, nullable=True)
    collect_minimal_data_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    retention_days_messages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retention_days_responses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retention_days_recordings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retention_days_transcripts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class OrganisationServiceCatalogItem(Base):
    __tablename__ = "organisation_service_catalog_items"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_organisation_service_catalog_org_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category_slug: Mapped[str] = mapped_column(String(80), ForeignKey("categories.slug"), nullable=False, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class OrganisationWorkflowConfig(Base):
    __tablename__ = "organisation_workflow_configs"
    __table_args__ = (UniqueConstraint("org_id", "workflow_key", name="uq_organisation_workflow_configs_org_workflow"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    workflow_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    channels_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    timing_rules_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    allowed_actions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    forbidden_actions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    escalation_rules_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    generated_profile_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    generated_prompt_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    workflow_summary_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

