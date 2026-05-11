from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    is_active: bool
    is_superuser: bool
    created_at: datetime


class PatientCreate(BaseModel):
    branch_id: str | None = None
    first_name: str
    last_name: str
    date_of_birth: date | None = None
    phone_e164: str | None = None
    email: str | None = None


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    branch_id: str | None
    first_name: str
    last_name: str
    date_of_birth: date | None
    phone_e164: str | None
    email: str | None
    created_at: datetime

