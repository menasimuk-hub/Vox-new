from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AppointmentCreate(BaseModel):
    branch_id: str | None = None
    patient_id: str | None = None
    scheduled_start: datetime
    scheduled_end: datetime | None = None
    status: str = "scheduled"
    value_gbp_pence: int | None = None
    treatment_label: str | None = None


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    branch_id: str | None
    patient_id: str | None
    scheduled_start: datetime
    scheduled_end: datetime | None
    status: str
    value_gbp_pence: int | None = None
    treatment_label: str | None = None
    created_at: datetime


class AppointmentUpdate(BaseModel):
    branch_id: str | None = None
    patient_id: str | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    status: str | None = None
    value_gbp_pence: int | None = None
    treatment_label: str | None = None

