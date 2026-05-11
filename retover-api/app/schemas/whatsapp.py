from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WhatsAppLogCreate(BaseModel):
    appointment_id: str | None = None
    patient_id: str | None = None
    provider: str = "twilio"
    status: str = "queued"
    direction: str = "outbound"
    to_number: str | None = None
    from_number: str | None = None
    body: str | None = None
    media_json: str | None = None
    raw_payload: str | None = None


class WhatsAppLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    org_id: str
    appointment_id: str | None
    patient_id: str | None
    patient_name: str | None = None
    branch_name: str | None = None
    appointment_scheduled_start: datetime | None = None
    provider: str
    external_message_id: str | None = None
    status: str
    direction: str = "outbound"
    to_number: str | None
    from_number: str | None = None
    body: str | None = None
    media_json: str | None = None
    raw_payload: str | None
    created_at: datetime

