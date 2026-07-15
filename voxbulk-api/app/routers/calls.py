from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.schemas.call import CallLogCreate, CallLogOut
from app.services.telnyx_voice_service import TelnyxExecutionService
from app.services.messaging_log_service import LogService
from app.services.recovery_service import RecoveryJobService
from app.workers.celery_app import celery_app
from sqlalchemy import select
from app.models.recovery_job import RecoveryJob
from app.models.dentally_appointment import DentallyAppointment
from app.models.patient import Patient
from app.models.branch import Branch

router = APIRouter(prefix="/calls", tags=["calls"])

@router.get("", response_model=list[CallLogOut])
def list_call_logs(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    return LogService.list_call_logs(db, principal.org_id)


@router.post("", response_model=CallLogOut)
def create_call_log(payload: CallLogCreate, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    try:
        return LogService.create_call_log(db, principal.org_id, **payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/start")
def start_telnyx_call(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    to_number = str(payload.get("to_number") or "").strip()
    if not to_number:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="to_number is required")
    try:
        log = TelnyxExecutionService.start_call(
            db,
            org_id=principal.org_id,
            to_number=to_number,
            appointment_id=(payload.get("appointment_id") or None),
            patient_id=(payload.get("patient_id") or None),
            user_id=principal.user_id,
            llm_prompt=(payload.get("llm_prompt") or None),
            agent_id=(payload.get("agent_id") or None),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {"ok": log.status != "failed", "log": log}


@router.get("/{log_id}", response_model=CallLogOut)
def get_call_log(log_id: int, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    obj = LogService.get_call_log(db, principal.org_id, log_id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call log not found")
    return obj


@router.get("/recovery/jobs/{job_id}")
def get_recovery_job(job_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    job = RecoveryJobService.get_job(db, org_id=principal.org_id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recovery job not found")
    return {
        "job_id": job.id,
        "appointment_id": job.dentally_appointment_id,
        "state": job.state,
        "attempts": job.attempts,
        "last_error": job.last_error,
        "provider": job.provider,
        "provider_ref": job.provider_ref,
        "provider_status": job.provider_status,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "updated_at": job.updated_at,
    }


@router.get("/recovery/tasks/{task_id}")
def get_task_status(task_id: str, principal=Depends(get_current_principal)):
    res = celery_app.AsyncResult(task_id)
    return {"task_id": task_id, "state": res.state, "result": res.result if res.successful() else None}


@router.get("/recovery/jobs")
def list_recovery_jobs(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    rows = db.execute(
        select(
            RecoveryJob,
            DentallyAppointment.id,
            DentallyAppointment.scheduled_start,
            DentallyAppointment.value_gbp_pence,
            DentallyAppointment.treatment_label,
            Patient.id,
            Patient.first_name,
            Patient.last_name,
            Branch.name,
        )
        .outerjoin(DentallyAppointment, DentallyAppointment.id == RecoveryJob.dentally_appointment_id)
        .outerjoin(Patient, Patient.id == DentallyAppointment.patient_id)
        .outerjoin(Branch, Branch.id == DentallyAppointment.branch_id)
        .where(RecoveryJob.org_id == principal.org_id)
        .order_by(RecoveryJob.created_at.desc())
        .limit(200)
    ).all()

    out = []
    for j, appt_id, appt_start, appt_value, appt_treatment, patient_id, p_first, p_last, branch_name in rows:
        patient_name = None
        if p_first or p_last:
            patient_name = f"{p_first or ''} {p_last or ''}".strip() or None
        out.append(
            {
                "job_id": j.id,
                "appointment_id": appt_id or j.dentally_appointment_id,
                "patient_id": patient_id,
                "patient_name": patient_name,
                "branch_name": branch_name,
                "appointment_scheduled_start": appt_start,
                "appointment_value_gbp_pence": appt_value,
                "treatment_label": appt_treatment,
                "state": j.state,
                "attempts": j.attempts,
                "last_error": j.last_error,
                "provider": j.provider,
                "provider_ref": j.provider_ref,
                "provider_status": j.provider_status,
                "created_at": j.created_at,
                "started_at": j.started_at,
                "finished_at": j.finished_at,
            }
        )
    return out


@router.get("/recovery/appointments/{appointment_id}/jobs")
def list_recovery_jobs_for_appointment(
    appointment_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    jobs = list(
        db.execute(
            select(RecoveryJob)
            .where(RecoveryJob.org_id == principal.org_id, RecoveryJob.dentally_appointment_id == appointment_id)
            .order_by(RecoveryJob.created_at.desc())
        ).scalars()
    )
    return [{"job_id": j.id, "state": j.state, "created_at": j.created_at} for j in jobs]

