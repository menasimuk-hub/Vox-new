from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.models.appointment import Appointment
from app.models.call_log import CallLog
from app.models.patient import Patient
from app.models.whatsapp_log import WhatsAppLog
from app.schemas.dashboard import DashboardMetricsOut
from app.workers.sync_tasks import dentally_sync_tenant
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/metrics", response_model=DashboardMetricsOut)
def metrics(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    org_id = principal.org_id

    total_patients = db.execute(select(func.count()).select_from(Patient).where(Patient.org_id == org_id)).scalar_one()
    total_appointments = db.execute(
        select(func.count()).select_from(Appointment).where(Appointment.org_id == org_id)
    ).scalar_one()
    total_call_logs = db.execute(select(func.count()).select_from(CallLog).where(CallLog.org_id == org_id)).scalar_one()
    total_whatsapp_logs = db.execute(
        select(func.count()).select_from(WhatsAppLog).where(WhatsAppLog.org_id == org_id)
    ).scalar_one()

    rows = db.execute(
        select(Appointment.status, func.count()).where(Appointment.org_id == org_id).group_by(Appointment.status)
    ).all()
    status_counts = {str(status): int(count) for status, count in rows}

    return DashboardMetricsOut(
        total_patients=int(total_patients),
        total_appointments=int(total_appointments),
        total_call_logs=int(total_call_logs),
        total_whatsapp_logs=int(total_whatsapp_logs),
        appointment_status_counts=status_counts,
    )


@router.get("/home-summary")
def home_summary(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    """KPI blocks for dashboard home — interview, survey, recovery (when enabled)."""
    from app.models.service_order import ServiceOrder
    from app.services.org_enabled_services import parse_enabled_services
    from app.services.recovery_service import OrganisationService
    from app.services.platform_catalog_service import ServiceOrderService

    org = OrganisationService.get_org(db, principal.org_id)
    enabled = parse_enabled_services(org.enabled_services_json if org else None)

    rows = list(
        db.execute(select(ServiceOrder).where(ServiceOrder.org_id == principal.org_id)).scalars().all()
    )
    interviews = [r for r in rows if r.service_code == "interview"]
    surveys = [r for r in rows if r.service_code == "survey"]

    int_live = sum(1 for r in interviews if ServiceOrderService.is_live_interview(r))
    int_finished = sum(1 for r in interviews if ServiceOrderService.is_finished_interview(r))
    int_archived = sum(1 for r in interviews if ServiceOrderService.is_archived_order(r))
    int_running = sum(1 for r in interviews if r.status == "running")
    int_candidates = sum(int(r.recipient_count or 0) for r in interviews if r.status in {"running", "completed"})

    sur_live = sum(1 for r in surveys if ServiceOrderService.is_live_survey(r))
    sur_finished = sum(1 for r in surveys if ServiceOrderService.is_finished_survey(r))
    sur_archived = sum(1 for r in surveys if ServiceOrderService.is_archived_order(r))
    sur_running = sum(1 for r in surveys if r.status == "running")
    sur_paused = sum(1 for r in surveys if r.status == "paused")
    sur_responses = 0
    sur_sent = 0
    for r in surveys:
        try:
            import json

            report = json.loads(r.report_json or "{}")
        except Exception:
            report = {}
        if isinstance(report, dict):
            sur_responses += int(report.get("responded") or report.get("completed") or 0)
            sur_sent += int(report.get("sent") or report.get("reached") or r.recipient_count or 0)

    total_patients = db.execute(
        select(func.count()).select_from(Patient).where(Patient.org_id == principal.org_id)
    ).scalar_one()
    status_rows = db.execute(
        select(Appointment.status, func.count())
        .where(Appointment.org_id == principal.org_id)
        .group_by(Appointment.status)
    ).all()
    queue_pending = sum(
        int(c)
        for st, c in status_rows
        if str(st) in {"pending", "missed", "cancelled", "no_show"}
    )

    return {
        "enabled_services": enabled,
        "interview": {
            "live": int_live,
            "finished": int_finished,
            "archived": int_archived,
            "running": int_running,
            "candidates": int_candidates,
        },
        "survey": {
            "live": sur_live,
            "finished": sur_finished,
            "archived": sur_archived,
            "running": sur_running,
            "paused": sur_paused,
            "responses": sur_responses,
            "sent": sur_sent,
            "completion_rate": round((sur_responses / sur_sent) * 100) if sur_sent else 0,
        },
        "recovery": {
            "queue_pending": int(queue_pending),
            "total_calls": int(
                db.execute(select(func.count()).select_from(CallLog).where(CallLog.org_id == principal.org_id)).scalar_one()
            ),
            "whatsapp_sent": int(
                db.execute(select(func.count()).select_from(WhatsAppLog).where(WhatsAppLog.org_id == principal.org_id)).scalar_one()
            ),
        },
        "total_patients": int(total_patients),
    }


@router.post("/dentally/sync")
def dentally_sync(principal=Depends(get_current_principal)):
    res = dentally_sync_tenant.delay(org_id=principal.org_id)
    return {"task_id": res.id}


@router.get("/dentally/sync/{task_id}")
def dentally_sync_status(task_id: str):
    res = celery_app.AsyncResult(task_id)
    return {"task_id": task_id, "state": res.state, "result": res.result if res.successful() else None}

