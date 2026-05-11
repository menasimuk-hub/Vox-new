from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.branch import Branch
from app.models.patient import Patient


class AppointmentService:
    @staticmethod
    def _validate_branch(db: Session, org_id: str, branch_id: str) -> None:
        branch = db.execute(select(Branch.id).where(Branch.id == branch_id, Branch.org_id == org_id)).scalar_one_or_none()
        if branch is None:
            raise ValueError("Invalid branch_id for tenant")

    @staticmethod
    def _validate_patient(db: Session, org_id: str, patient_id: str) -> None:
        patient = db.execute(select(Patient.id).where(Patient.id == patient_id, Patient.org_id == org_id)).scalar_one_or_none()
        if patient is None:
            raise ValueError("Invalid patient_id for tenant")

    @staticmethod
    def list_appointments(db: Session, org_id: str) -> list[Appointment]:
        return list(
            db.execute(select(Appointment).where(Appointment.org_id == org_id).order_by(Appointment.scheduled_start.desc())).scalars()
        )

    @staticmethod
    def get_appointment(db: Session, org_id: str, appointment_id: str) -> Appointment | None:
        return db.execute(
            select(Appointment).where(Appointment.id == appointment_id, Appointment.org_id == org_id)
        ).scalar_one_or_none()

    @staticmethod
    def create_appointment(
        db: Session,
        org_id: str,
        *,
        branch_id: str | None,
        patient_id: str | None,
        scheduled_start,
        scheduled_end,
        status: str,
        value_gbp_pence: int | None = None,
        treatment_label: str | None = None,
    ) -> Appointment:
        if branch_id:
            AppointmentService._validate_branch(db, org_id, branch_id)
        if patient_id:
            AppointmentService._validate_patient(db, org_id, patient_id)

        appt = Appointment(
            org_id=org_id,
            branch_id=branch_id,
            patient_id=patient_id,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
            status=status,
            value_gbp_pence=value_gbp_pence,
            treatment_label=(str(treatment_label).strip() or None) if treatment_label is not None else None,
        )
        db.add(appt)
        db.commit()
        db.refresh(appt)
        return appt

    @staticmethod
    def update_appointment(
        db: Session,
        org_id: str,
        appointment_id: str,
        *,
        branch_id: str | None = None,
        patient_id: str | None = None,
        scheduled_start=None,
        scheduled_end=None,
        status: str | None = None,
        value_gbp_pence: int | None = None,
        treatment_label: str | None = None,
    ) -> Appointment | None:
        appt = AppointmentService.get_appointment(db, org_id, appointment_id)
        if appt is None:
            return None

        if branch_id is not None:
            if branch_id:
                AppointmentService._validate_branch(db, org_id, branch_id)
            appt.branch_id = branch_id

        if patient_id is not None:
            if patient_id:
                AppointmentService._validate_patient(db, org_id, patient_id)
            appt.patient_id = patient_id

        if scheduled_start is not None:
            appt.scheduled_start = scheduled_start
        if scheduled_end is not None:
            appt.scheduled_end = scheduled_end
        if status is not None:
            appt.status = status

        if value_gbp_pence is not None:
            appt.value_gbp_pence = value_gbp_pence

        if treatment_label is not None:
            appt.treatment_label = str(treatment_label).strip() or None

        db.add(appt)
        db.commit()
        db.refresh(appt)
        return appt

