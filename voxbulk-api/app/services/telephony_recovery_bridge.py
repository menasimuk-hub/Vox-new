from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dentally_appointment import DentallyAppointment
from app.models.recovery_job import RecoveryJob
from app.services.recovery_service import RecoveryStateMachine


def _map_call_status(call_status: str) -> tuple[str | None, str | None, str | None]:
    status = str(call_status or "").strip().lower()
    if status in {"queued", "initiated", "ringing", "in-progress", "answered", "dialing", "bridging", "active"}:
        return "calling", "calling", None
    if status in {"completed", "hangup", "ended"}:
        return "messaged", "messaged", None
    if status in {"busy", "no-answer", "failed", "canceled", "cancelled", "machine_detected"}:
        return "failed", "failed", f"Call status: {status}"
    return None, None, None


def apply_call_status_to_recovery(
    db: Session,
    *,
    provider: str,
    provider_ref: str,
    call_status: str,
) -> RecoveryJob | None:
    job = db.execute(
        select(RecoveryJob).where(RecoveryJob.provider == provider, RecoveryJob.provider_ref == provider_ref)
    ).scalar_one_or_none()
    if job is None:
        return None

    appt = db.execute(
        select(DentallyAppointment).where(DentallyAppointment.id == job.dentally_appointment_id, DentallyAppointment.org_id == job.org_id)
    ).scalar_one()

    desired_appt_state, desired_job_state, terminal_error = _map_call_status(call_status)
    job.provider_status = str(call_status)

    appt_rank = {"pending": 0, "queued": 1, "calling": 2, "messaged": 3, "recovered": 4, "failed": 4, "skipped": 4}
    if desired_appt_state is not None:
        if appt_rank.get(desired_appt_state, 0) >= appt_rank.get(appt.recovery_state, 0):
            try:
                if desired_appt_state != appt.recovery_state:
                    RecoveryStateMachine.transition(
                        db,
                        appointment=appt,
                        to_state=desired_appt_state,
                        error=terminal_error,
                    )
            except ValueError:
                pass

    if desired_job_state is not None:
        job_rank = {"queued": 0, "calling": 1, "messaged": 2, "recovered": 3, "failed": 3, "skipped": 3}
        if job_rank.get(desired_job_state, 0) >= job_rank.get(job.state, 0):
            job.state = desired_job_state
            if terminal_error:
                job.last_error = terminal_error
            if desired_job_state in {"failed", "skipped", "messaged", "recovered"}:
                job.finished_at = job.finished_at or appt.recovery_updated_at

    db.add(job)
    return job


def apply_message_status_to_recovery(
    db: Session,
    *,
    provider: str,
    provider_ref: str,
    message_status: str,
) -> RecoveryJob | None:
    job = db.execute(
        select(RecoveryJob).where(RecoveryJob.provider == provider, RecoveryJob.provider_ref == provider_ref)
    ).scalar_one_or_none()
    if job is None:
        return None
    job.provider_status = str(message_status)
    status = str(message_status or "").strip().lower()
    if status in {"delivered", "sent", "queued", "sending"}:
        job.state = "messaged"
    elif status in {"failed", "undelivered"}:
        job.state = "failed"
        job.last_error = f"Message status: {status}"
        job.finished_at = job.finished_at or job.updated_at
    db.add(job)
    return job
