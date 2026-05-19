from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SupportedServiceAPIOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    display_name: str
    category_slug: str
    short_description: str | None = None
    status: str
    is_active: bool
    is_recommended: bool
    api_difficulty: str | None = None
    docs_text: str | None = None
    sort_order: int
    api_setup_exists: bool = False
    created_at: datetime
    updated_at: datetime


class SupportedServiceAPIIn(BaseModel):
    slug: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=160)
    category_slug: str = Field(min_length=1, max_length=80)
    short_description: str | None = None
    status: str = "active"
    is_active: bool = True
    is_recommended: bool = False
    api_difficulty: str | None = None
    docs_text: str | None = None
    sort_order: int = 100


class SupportedServiceAPIUpdate(BaseModel):
    display_name: str | None = None
    category_slug: str | None = None
    short_description: str | None = None
    status: str | None = None
    is_active: bool | None = None
    is_recommended: bool | None = None
    api_difficulty: str | None = None
    docs_text: str | None = None
    sort_order: int | None = None


class CategoryOptionOut(BaseModel):
    id: str
    slug: str
    name: str
    description: str | None = None


class OnboardingStatusOut(BaseModel):
    org_id: str
    onboarding_state: str
    onboarding_complete: bool
    category_slug: str | None = None
    category_id: str | None = None
    booking_software_slug: str | None = None
    next_step: str
    completed_at: datetime | None = None


class SelectCategoryIn(BaseModel):
    category_slug: str
    confirm_change: bool = False


class SelectSoftwareIn(BaseModel):
    software_slug: str
    confirm_change: bool = False


class AIIdentityIn(BaseModel):
    assistant_name: str | None = None
    organisation_name: str | None = None
    tone: str | None = None
    humor_level: str | None = None
    languages: list[str] | None = None
    terminology_label: str | None = None
    disclose_ai: bool | None = None


class ComplianceConfigIn(BaseModel):
    outbound_call_windows: dict[str, Any] | None = None
    whatsapp_windows: dict[str, Any] | None = None
    weekend_allowed: bool | None = None
    ai_disclosure_wording: str | None = None
    opt_out_wording: str | None = None
    escalation_destination: str | None = None
    contact_preference_rules: dict[str, Any] | None = None


class WorkflowConfigIn(BaseModel):
    workflow_key: str
    enabled: bool = True
    channels: list[str] = Field(default_factory=list)
    timing_rules: dict[str, Any] = Field(default_factory=dict)
    allowed_actions: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    escalation_rules: list[str] = Field(default_factory=list)


class WizardSaveStepIn(BaseModel):
    step: str
    services: list[str] | None = None
    custom_services: list[str] | None = None
    ai_identity: AIIdentityIn | None = None
    compliance: ComplianceConfigIn | None = None
    workflows: list[WorkflowConfigIn] | None = None


class WizardCompleteIn(WizardSaveStepIn):
    pass


class WorkflowPromptOut(BaseModel):
    workflow_key: str
    enabled: bool
    channels: list[str]
    generated_profile: dict[str, Any]
    generated_prompt_preview: str
    workflow_summary_preview: str


class OrganisationAIConfigOut(BaseModel):
    status: OnboardingStatusOut
    ai_identity: dict[str, Any] | None = None
    compliance: dict[str, Any] | None = None
    services: list[str]
    workflows: list[WorkflowPromptOut]

