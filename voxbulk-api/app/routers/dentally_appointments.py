from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.schemas.dentally_appointment import DentallyAppointmentCreate, DentallyAppointmentOut, DentallyAppointmentUpdate
from app.services.call_engine import DentallyAppointmentService
from app.services.recovery_service import RecoveryJobService
from app.workers.call_tasks import process_recovery_job

router = APIRouter(prefix="/dentally/appointments", tags=["dentally-appointments"])


@router.get("", response_model=list[DentallyAppointmentOut])
def list_dentally_appointments(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    return DentallyAppointmentService.list_appointments(db, principal.org_id)


@router.post("", response_model=DentallyAppointmentOut)
def create_dentally_appointment(
    payload: DentallyAppointmentCreate, db: Session = Depends(get_db), principal=Depends(get_current_principal)
):
    try:
        return DentallyAppointmentService.create_appointment(
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{appointment_id}", response_model=DentallyAppointmentOut)
def get_dentally_appointment(appointment_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    appt = DentallyAppointmentService.get_appointment(db, principal.org_id, appointment_id)
    if appt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return appt


@router.patch("/{appointment_id}", response_model=DentallyAppointmentOut)
def update_dentally_appointment(
    appointment_id: str,
    payload: DentallyAppointmentUpdate,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    try:
        appt = DentallyAppointmentService.update_appointment(
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    if appt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return appt


@router.post("/{appointment_id}/recovery")
def enqueue_dentally_recovery(
    appointment_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)
):
    try:
        job = RecoveryJobService.enqueue_for_appointment(
            db,
            org_id=principal.org_id,
            appointment_id=appointment_id,
            requested_by_user_id=principal.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    async_result = process_recovery_job.delay(job_id=job.id)
    return {"job_id": job.id, "task_id": async_result.id, "state": job.state}
