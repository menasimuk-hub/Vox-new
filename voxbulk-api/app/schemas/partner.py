from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PartnerScreeningCreateIn(BaseModel):
    partner_reference_id: str = Field(min_length=1, max_length=120)
    job_title: str = Field(min_length=1, max_length=300)
    screening_questions: list[str] = Field(default_factory=list)
    candidate_name: str = Field(min_length=1, max_length=200)
    candidate_phone: str = Field(min_length=5, max_length=40)
    preferred_language: Literal["en", "ar"] = "en"
    callback_url: str | None = None
    job_description: str | None = None
    candidate_email: str | None = None


class PartnerScreeningCreateOut(BaseModel):
    status: str
    screening_id: str
    partner_reference_id: str
    screening_link: str
    estimated_completion_minutes: int


class PartnerResultIn(BaseModel):
    partner_reference_id: str = Field(min_length=1, max_length=120)
    candidate_score: int = Field(ge=0, le=100)
    status: Literal["passed", "review", "rejected"]
    report_url: str | None = None
    call_duration_minutes: float | None = None
    total_charge_amount: float | None = None
    screening_id: str | None = None


class PartnerResultOut(BaseModel):
    status: str
    received: bool
    screening_id: str | None = None
    partner_reference_id: str


class PartnerHealthOut(BaseModel):
    status: str
    service: str = "partner-api"
    version: str = "v1"


class PartnerProviderUpdateIn(BaseModel):
    enabled: bool | None = None
    mode: Literal["sandbox", "live"] | None = None
    release_mode: Literal["testing", "live"] | None = None
    mapped_org_id: str | None = None
    result_webhook_url: str | None = None
    webhook_secret: str | None = None
    connection_fee_gbp: float | None = None
    per_minute_gbp: float | None = None
    commission_pct: float | None = None
    est_cost_per_completed_gbp: float | None = None
    config: dict[str, Any] | None = None
