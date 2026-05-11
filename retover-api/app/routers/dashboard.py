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


@router.post("/dentally/sync")
def dentally_sync(principal=Depends(get_current_principal)):
    res = dentally_sync_tenant.delay(org_id=principal.org_id)
    return {"task_id": res.id}


@router.get("/dentally/sync/{task_id}")
def dentally_sync_status(task_id: str):
    res = celery_app.AsyncResult(task_id)
    return {"task_id": task_id, "state": res.state, "result": res.result if res.successful() else None}

