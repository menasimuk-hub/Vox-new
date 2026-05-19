from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CallLogCreate(BaseModel):
    appointment_id: str | None = None
    patient_id: str | None = None
    user_id: str | None = None
    provider: str = "twilio"
    direction: str = "outbound"
    status: str = "queued"
    to_number: str | None = None
    from_number: str | None = None
    recording_url: str | None = None
    media_stream_id: str | None = None
    llm_prompt: str | None = None
    llm_response: str | None = None
    transcript_text: str | None = None
    raw_payload: str | None = None


class CallLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    org_id: str
    user_id: str | None = None
    appointment_id: str | None
    patient_id: str | None
    patient_name: str | None = None
    branch_name: str | None = None
    appointment_scheduled_start: datetime | None = None
    provider: str
    external_call_id: str | None = None
    direction: str
    status: str
    to_number: str | None
    from_number: str | None
    recording_url: str | None = None
    media_stream_id: str | None = None
    llm_prompt: str | None = None
    llm_response: str | None = None
    transcript_text: str | None = None
    raw_payload: str | None
    created_at: datetime
    started_at: datetime | None = None
    answered_at: datetime | None = None
    ended_at: datetime | None = None
    last_status_at: datetime | None = None

