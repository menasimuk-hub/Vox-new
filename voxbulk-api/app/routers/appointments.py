"""CRM AI Appointment Manager dashboard API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.models.agent import AgentDefinition
from app.models.organisation import Organisation
from app.schemas.appointments import (
    AppointmentAgentOut,
    AppointmentBillingEligibilityOut,
    AppointmentCreateIn,
    AppointmentDailyBreakdownOut,
    AppointmentDetailOut,
    AppointmentLogOut,
    AppointmentOut,
    AppointmentPatchIn,
    AppointmentReportByBranchOut,
    AppointmentReportByCrmOut,
    AppointmentReportPipelineOut,
    AppointmentReportConfirmationMethodsOut,
    AppointmentReportMetricsOut,
    AppointmentReportSummaryOut,
    AppointmentSettingsOut,
    AppointmentSettingsPatchIn,
    AppointmentStatusPatchIn,
    AppointmentTemplateOut,
)
from app.services.appointment_call_service import handle_appointment_telnyx_event
from app.services.appointment_crm_sync_service import sync_org_appointments
from app.services.appointment_report_service import (
    by_branch,
    by_crm,
    confirmation_methods,
    daily_breakdown,
    pipeline_status,
    summary,
    summary_metrics,
)
from app.services.appointment_service import AppointmentService
from app.services.appointment_settings_service import get_config, save_config
from app.services.appointment_billing_service import AppointmentBillingError, AppointmentBillingService
from app.services.appointment_calendar_service import calendar_status
from app.services.appointment_whatsapp_template_service import AppointmentWhatsappTemplateService
from app.services.appointment_wa_inbound_service import try_handle_inbound
from app.services.org_enabled_services import is_service_enabled, org_service_maps

router = APIRouter(prefix="/appointments", tags=["appointments"])


def _require_appointments_enabled(db: Session, org_id: str) -> Organisation:
    org = db.get(Organisation, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    _allowed, _enabled, visible = org_service_maps(org, db)
    if not is_service_enabled(visible, "appointments"):
        raise HTTPException(status_code=403, detail="Appointments is not enabled for this organisation.")
    return org


@router.get("/billing/eligibility", response_model=AppointmentBillingEligibilityOut)
def get_billing_eligibility(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    org = _require_appointments_enabled(db, principal.org_id)
    return AppointmentBillingService.eligibility(db, org)


@router.get("/reports/summary", response_model=AppointmentReportSummaryOut)
def get_report_summary(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    org = _require_appointments_enabled(db, principal.org_id)
    return summary(db, principal.org_id)


@router.get("/reports/daily", response_model=AppointmentDailyBreakdownOut)
def get_report_daily(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    org = _require_appointments_enabled(db, principal.org_id)
    return daily_breakdown(db, principal.org_id, days=days)


@router.get("/reports/confirmation-methods", response_model=AppointmentReportConfirmationMethodsOut)
def get_report_confirmation_methods(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    org = _require_appointments_enabled(db, principal.org_id)
    return confirmation_methods(db, principal.org_id)


@router.get("/reports/pipeline", response_model=AppointmentReportPipelineOut)
def get_report_pipeline(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    org = _require_appointments_enabled(db, principal.org_id)
    return pipeline_status(db, principal.org_id)


@router.get("/reports/by-crm", response_model=AppointmentReportByCrmOut)
def get_report_by_crm(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    org = _require_appointments_enabled(db, principal.org_id)
    return by_crm(db, principal.org_id)


@router.get("/reports/by-branch", response_model=AppointmentReportByBranchOut)
def get_report_by_branch(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    org = _require_appointments_enabled(db, principal.org_id)
    return by_branch(db, principal.org_id)


@router.get("/reports/metrics", response_model=AppointmentReportMetricsOut)
def get_report_metrics(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    org = _require_appointments_enabled(db, principal.org_id)
    return summary_metrics(db, principal.org_id)


@router.get("/agents", response_model=list[AppointmentAgentOut])
def list_appointment_agents(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    org = _require_appointments_enabled(db, principal.org_id)
    rows = db.query(AgentDefinition).filter(
        AgentDefinition.is_active.is_(True),
        AgentDefinition.supports_appointment.is_(True),
    ).order_by(AgentDefinition.is_default_appointment.desc(), AgentDefinition.name.asc()).all()
    return [
        AppointmentAgentOut(
            id=a.id,
            name=a.name or "Agent",
            voice_label=a.voice_label,
            voice_type_label=a.voice_type_label,
            is_platform_default=bool(a.is_default_appointment),
        )
        for a in rows
    ]


@router.get("/settings/calendar-status")
def get_calendar_status(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_appointments_enabled(db, principal.org_id)
    return calendar_status(db, principal.org_id)


@router.get("/settings", response_model=AppointmentSettingsOut)
def get_settings(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    org = _require_appointments_enabled(db, principal.org_id)
    return get_config(db, principal.org_id)


@router.patch("/settings", response_model=AppointmentSettingsOut)
def patch_settings(
    payload: AppointmentSettingsPatchIn,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    org = _require_appointments_enabled(db, principal.org_id)
    data = payload.model_dump(exclude_unset=True)
    activating = (
        data.get("setup_complete") is True
        or data.get("wa_enabled") is True
        or data.get("call_enabled") is True
    )
    if activating:
        try:
            AppointmentBillingService.assert_can_operate(db, principal.org_id)
        except AppointmentBillingError as e:
            raise HTTPException(status_code=402, detail=str(e)) from e
    try:
        return save_config(db, principal.org_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/templates", response_model=list[AppointmentTemplateOut])
def list_templates(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    org = _require_appointments_enabled(db, principal.org_id)
    cfg = get_config(db, principal.org_id)
    configured = str(cfg.get("wa_template_name") or "appt_confirm_v1")
    items = [
        AppointmentTemplateOut(**row)
        for row in AppointmentWhatsappTemplateService.list_customer_templates(db)
    ]
    if configured not in {t.name for t in items}:
        items.insert(
            0,
            AppointmentTemplateOut(name=configured, label=configured, description="Configured template"),
        )
    return items


@router.get("", response_model=list[AppointmentOut])
def list_appointments(
    status: str | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    org = _require_appointments_enabled(db, principal.org_id)
    return AppointmentService.list_appointments(db, principal.org_id, status=status)


@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def create_appointment(
    payload: AppointmentCreateIn,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    org = _require_appointments_enabled(db, principal.org_id)
    try:
        return AppointmentService.create_appointment(db, principal.org_id, payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/sync-crm")
def sync_crm(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    org = _require_appointments_enabled(db, principal.org_id)
    try:
        result = sync_org_appointments(db, principal.org_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, **result}


@router.get("/{appointment_id}", response_model=AppointmentDetailOut)
def get_appointment(appointment_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    org = _require_appointments_enabled(db, principal.org_id)
    detail = AppointmentService.get_detail(db, principal.org_id, appointment_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    appt = detail["appointment"]
    logs = detail["logs"]
    return AppointmentDetailOut.model_validate(appt, from_attributes=True).model_copy(
        update={"logs": [AppointmentLogOut.model_validate(x, from_attributes=True) for x in logs]}
    )


@router.patch("/{appointment_id}", response_model=AppointmentOut)
def patch_appointment(
    appointment_id: str,
    payload: AppointmentPatchIn,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    org = _require_appointments_enabled(db, principal.org_id)
    try:
        appt = AppointmentService.patch_appointment(
            db, principal.org_id, appointment_id, payload.model_dump(exclude_unset=True)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if appt is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appt


@router.patch("/{appointment_id}/status", response_model=AppointmentOut)
def patch_appointment_status(
    appointment_id: str,
    payload: AppointmentStatusPatchIn,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    org = _require_appointments_enabled(db, principal.org_id)
    try:
        appt = AppointmentService.patch_status(db, principal.org_id, appointment_id, payload.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if appt is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appt


@router.post("/{appointment_id}/call")
def trigger_call(appointment_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    org = _require_appointments_enabled(db, principal.org_id)
    try:
        result = AppointmentService.trigger_call(db, principal.org_id, appointment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"ok": bool(result.get("ok")), **result}


@router.post("/wa-webhook")
async def wa_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    record = payload.get("data") or payload
    if isinstance(record, dict) and isinstance(record.get("payload"), dict):
        record = record["payload"]
    from_phone = str(record.get("from") or record.get("from_phone") or "").strip()
    body = str(record.get("text") or record.get("body") or "").strip()
    org_id = str(payload.get("org_id") or record.get("org_id") or "").strip() or None
    if not from_phone or not org_id:
        return {"handled": False, "reason": "missing_from_or_org"}
    handled = try_handle_inbound(db, from_phone, body, org_id)
    return {"handled": handled}


@router.post("/call-webhook")
async def call_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    handled = handle_appointment_telnyx_event(db, payload if isinstance(payload, dict) else {})
    return {"handled": handled}
