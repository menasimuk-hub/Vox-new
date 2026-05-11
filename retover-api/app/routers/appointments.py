from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.schemas.appointment import AppointmentCreate, AppointmentOut, AppointmentUpdate
from app.services.call_engine import AppointmentService
from app.services.recovery_service import RecoveryJobService
from app.workers.call_tasks import process_recovery_job

router = APIRouter(prefix="/appointments", tags=["appointments"])

@router.get("", response_model=list[AppointmentOut])
def list_appointments(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    return AppointmentService.list_appointments(db, principal.org_id)


@router.post("", response_model=AppointmentOut)
def create_appointment(payload: AppointmentCreate, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    try:
        return AppointmentService.create_appointment(
            db,
            principal.org_id,
            branch_id=payload.branch_id,
            patient_id=payload.patient_id,
            scheduled_start=payload.scheduled_start,
            scheduled_end=payload.scheduled_end,
            status=payload.status,
            value_gbp_pence=payload.value_gbp_pence,
            treatment_label=payload.treatment_label,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{appointment_id}", response_model=AppointmentOut)
def get_appointment(appointment_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    appt = AppointmentService.get_appointment(db, principal.org_id, appointment_id)
    if appt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return appt


@router.patch("/{appointment_id}", response_model=AppointmentOut)
def update_appointment(
    appointment_id: str,
    payload: AppointmentUpdate,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    try:
        appt = AppointmentService.update_appointment(
            db,
            principal.org_id,
            appointment_id,
            branch_id=payload.branch_id,
            patient_id=payload.patient_id,
            scheduled_start=payload.scheduled_start,
            scheduled_end=payload.scheduled_end,
            status=payload.status,
            value_gbp_pence=payload.value_gbp_pence,
            treatment_label=payload.treatment_label,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if appt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return appt


@router.post("/{appointment_id}/recovery")
def enqueue_recovery(appointment_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    try:
        job = RecoveryJobService.enqueue_for_appointment(
            db,
            org_id=principal.org_id,
            appointment_id=appointment_id,
            requested_by_user_id=principal.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    # enqueue async processing (idempotent job)
    async_result = process_recovery_job.delay(job_id=job.id)
    return {"job_id": job.id, "task_id": async_result.id, "state": job.state}

