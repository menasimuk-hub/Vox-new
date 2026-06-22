from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AppointmentLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    appointment_id: str
    event_type: str
    detail_json: str | None = None
    created_at: datetime


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    contact_name: str
    contact_phone: str
    contact_email: str | None = None
    appointment_datetime: datetime
    timezone: str
    location: str | None = None
    branch: str | None = None
    service_type: str | None = None
    status: str
    crm_source: str
    crm_record_id: str | None = None
    wa_confirmation_sent_at: datetime | None = None
    wa_confirmation_status: str | None = None
    call_triggered_at: datetime | None = None
    call_outcome: str | None = None
    rescheduled_to_datetime: datetime | None = None
    rescheduled_from_id: str | None = None
    confirmation_channel: str | None = None
    confirmed_at: datetime | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class AppointmentDetailOut(AppointmentOut):
    logs: list[AppointmentLogOut] = Field(default_factory=list)


class AppointmentCreateIn(BaseModel):
    contact_name: str
    contact_phone: str
    contact_email: str | None = None
    appointment_datetime: datetime
    timezone: str = "Europe/London"
    location: str | None = None
    branch: str | None = None
    service_type: str | None = None
    status: str = "scheduled"
    crm_source: str = "manual"
    crm_record_id: str | None = None
    notes: str | None = None


class AppointmentPatchIn(BaseModel):
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    appointment_datetime: datetime | None = None
    timezone: str | None = None
    location: str | None = None
    branch: str | None = None
    service_type: str | None = None
    notes: str | None = None


class AppointmentStatusPatchIn(BaseModel):
    status: str


class ReminderStepIn(BaseModel):
    hours_before: int = Field(ge=0)
    channel: str
    template_name: str | None = None


class AppointmentSettingsOut(BaseModel):
    setup_complete: bool = False
    workspace_name: str = ""
    crm_provider: str = "hubspot"
    crm_object: str = "contacts"
    crm_date_property: str = "appointment_date"
    sync_interval_minutes: int = 60
    appointment_agent_id: str | None = None
    outreach_window_start: str = "09:00"
    outreach_window_end: str = "16:00"
    wa_template_name: str
    wa_send_hours_before: int
    call_hours_before: int
    wa_enabled: bool
    call_enabled: bool
    reminder_sequence_json: list[dict] = Field(default_factory=list)


class AppointmentSettingsPatchIn(BaseModel):
    setup_complete: bool | None = None
    workspace_name: str | None = None
    crm_provider: str | None = None
    crm_object: str | None = None
    crm_date_property: str | None = None
    sync_interval_minutes: int | None = Field(default=None, ge=5)
    appointment_agent_id: str | None = None
    outreach_window_start: str | None = None
    outreach_window_end: str | None = None
    wa_template_name: str | None = None
    wa_send_hours_before: int | None = Field(default=None, ge=1)
    call_hours_before: int | None = Field(default=None, ge=1)
    wa_enabled: bool | None = None
    call_enabled: bool | None = None
    reminder_sequence_json: list[dict] | None = None


class AppointmentReportSummaryOut(BaseModel):
    total: int
    scheduled: int
    confirmed: int
    rescheduled: int
    cancelled: int
    no_show: int
    wa_sent: int
    calls_triggered: int


class AppointmentDailyBreakdownItem(BaseModel):
    date: str
    total: int
    confirmed: int
    cancelled: int
    no_show: int


class AppointmentDailyBreakdownOut(BaseModel):
    items: list[AppointmentDailyBreakdownItem] = Field(default_factory=list)


class AppointmentTemplateOut(BaseModel):
    name: str
    label: str
    description: str | None = None
    body: str | None = None
    footer: str | None = None
    buttons: list[dict] = Field(default_factory=list)


class AppointmentAgentOut(BaseModel):
    id: str
    name: str
    voice_label: str | None = None
    voice_type_label: str | None = None
    is_platform_default: bool = False


class AppointmentReportByCrmOut(BaseModel):
    items: list[dict] = Field(default_factory=list)


class AppointmentReportByBranchOut(BaseModel):
    items: list[dict] = Field(default_factory=list)


class AppointmentReportConfirmationMethodsOut(BaseModel):
    items: list[dict] = Field(default_factory=list)


class AppointmentReportPipelineOut(BaseModel):
    items: list[dict] = Field(default_factory=list)
    outreach_window_start: str = "09:00"
    outreach_window_end: str = "16:00"


class AppointmentReportMetricsOut(BaseModel):
    avg_hours_to_confirm: float | None = None
    wa_sent: int = 0
    calls_made: int = 0
    call_answer_rate: float | None = None
    rescheduled_kept_rate: float | None = None
