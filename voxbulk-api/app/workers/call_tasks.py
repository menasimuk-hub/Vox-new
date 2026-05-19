from __future__ import annotations

from datetime import datetime

from app.core.logging import get_logger
from app.core.database import get_sessionmaker
from sqlalchemy import select

from app.models.recovery_job import RecoveryJob
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.call_log import CallLog
from app.models.whatsapp_log import WhatsAppLog
from app.workers.celery_app import celery_app
from app.services.recovery_service import RecoveryStateMachine
from app.services.twilio_service import TwilioAdapter, TwilioCallerIdService, TwilioWhatsAppAdapter
from app.utils.ofcom import is_within_calling_window, now_uk
from app.services.provider_settings import ProviderSettingsService


logger = get_logger(__name__)


@celery_app.task(name="recovery.enqueue_appointment")
def process_recovery_job(*, job_id: str) -> dict:
    """
    Minimal async recovery state machine.

    States: queued -> processing -> completed|failed
    """
    with get_sessionmaker()() as db:
        twilio_cfg, twilio_enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="twilio")
        job = db.execute(select(RecoveryJob).where(RecoveryJob.id == job_id)).scalar_one()
        appt = db.execute(
            select(Appointment).where(Appointment.id == job.appointment_id, Appointment.org_id == job.org_id)
        ).scalar_one()

        if appt.recovery_state in RecoveryStateMachine.TERMINAL:
            return {"status": appt.recovery_state, "job_id": job.id}

        # Basic compliance hook: time window gating.
        if not is_within_calling_window(now_uk()):
            job.state = "skipped"
            job.last_error = "Outside contact window"
            RecoveryStateMachine.transition(db, appointment=appt, to_state="skipped", error=job.last_error)
            job.finished_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
            return {"status": job.state, "job_id": job.id}

        job.attempts += 1
        job.state = "calling"
        if job.started_at is None:
            job.started_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        db.add(job)
        RecoveryStateMachine.transition(db, appointment=appt, to_state="calling")
        db.commit()

        # Safe provider-aware stub: never claim success. We can determine "configured vs not".
        if appt.patient_id:
            patient = db.execute(
                select(Patient).where(Patient.id == appt.patient_id, Patient.org_id == job.org_id)
            ).scalar_one_or_none()
        else:
            patient = None

        if patient is None or not patient.phone_e164:
            job.state = "skipped"
            RecoveryStateMachine.transition(db, appointment=appt, to_state="skipped", error="No patient phone on record")
        else:
            cfg = twilio_cfg if twilio_enabled else None
            caller_id = TwilioCallerIdService.verified_caller_id_for_user(db, user_id=job.requested_by_user_id)
            res = TwilioAdapter.start_outbound_call(
                to_number=patient.phone_e164,
                from_number=caller_id,
                config=cfg,
            )
            if res.ok and res.external_id:
                job.provider = "twilio"
                job.provider_ref = res.external_id
                job.provider_status = res.status
                job.state = "calling"
                # Ensure call log exists for tracking
                db.add(
                    CallLog(
                        org_id=job.org_id,
                        appointment_id=job.appointment_id,
                        patient_id=appt.patient_id,
                        provider="twilio",
                        external_call_id=res.external_id,
                        direction="outbound",
                        status=res.status,
                        to_number=patient.phone_e164,
                    )
                )
                # leave appointment in calling until callback updates it
                RecoveryStateMachine.transition(db, appointment=appt, to_state="calling")
            else:
                # Fallback: WhatsApp message attempt (minimal, explicit).
                wa = TwilioWhatsAppAdapter.send_message(
                    to_number=patient.phone_e164,
                    body="VOXBULK: we noticed you may have availability to reschedule. Reply to confirm.",
                    config=twilio_cfg if twilio_enabled else None,
                )
                if wa.ok and wa.external_id:
                    job.provider = "twilio_whatsapp"
                    job.provider_ref = wa.external_id
                    job.provider_status = wa.status
                    job.state = "messaged"
                    db.add(
                        WhatsAppLog(
                            org_id=job.org_id,
                            appointment_id=job.appointment_id,
                            patient_id=appt.patient_id,
                            provider="twilio",
                            external_message_id=wa.external_id,
                            status=wa.status,
                            to_number=patient.phone_e164,
                        )
                    )
                    RecoveryStateMachine.transition(db, appointment=appt, to_state="messaged")
                else:
                    job.last_error = (res.detail or res.status) + " | " + (wa.detail or wa.status)
                    job.state = "failed"
                    RecoveryStateMachine.transition(db, appointment=appt, to_state="failed", error=job.last_error)

        job.updated_at = datetime.utcnow()
        if job.state in {"failed", "skipped", "messaged"}:
            job.finished_at = datetime.utcnow()
        db.add(job)
        db.commit()

        logger.info(
            "recovery_finished",
            extra={"org_id": job.org_id, "appointment_id": job.appointment_id, "job_id": job.id, "state": job.state},
        )
        return {"status": job.state, "job_id": job.id}

