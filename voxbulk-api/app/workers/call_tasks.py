from __future__ import annotations

from datetime import datetime

from app.core.logging import get_logger
from app.core.database import get_sessionmaker
from sqlalchemy import select

from app.models.recovery_job import RecoveryJob
from app.models.appointment import Appointment
from app.models.call_log import CallLog
from app.models.whatsapp_log import WhatsAppLog
from app.workers.celery_app import celery_app
from app.services.recovery_service import RecoveryStateMachine
from app.services.telnyx_messaging_service import TelnyxMessagingService
from app.services.telnyx_voice_service import TelnyxCallerIdService, TelnyxVoiceAdapter, telnyx_outbound_caller_id
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
        telnyx_cfg, telnyx_enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
        job = db.execute(select(RecoveryJob).where(RecoveryJob.id == job_id)).scalar_one()
        appt = db.execute(
            select(Appointment).where(Appointment.id == job.appointment_id, Appointment.org_id == job.org_id)
        ).scalar_one()

        if appt.recovery_state in RecoveryStateMachine.TERMINAL:
            return {"status": appt.recovery_state, "job_id": job.id}

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

        from app.models.patient import Patient

        if appt.patient_id:
            patient = db.execute(
                select(Patient).where(Patient.id == appt.patient_id, Patient.org_id == job.org_id)
            ).scalar_one_or_none()
        else:
            patient = None

        if patient is None or not patient.phone_e164:
            job.state = "skipped"
            RecoveryStateMachine.transition(db, appointment=appt, to_state="skipped", error="No patient phone on record")
        elif not telnyx_enabled:
            job.state = "failed"
            job.last_error = "Telnyx integration is disabled"
            RecoveryStateMachine.transition(db, appointment=appt, to_state="failed", error=job.last_error)
        else:
            config = ProviderSettingsService._validate_telnyx_config(telnyx_cfg or {})
            caller_id = TelnyxCallerIdService.verified_caller_id_for_user(db, user_id=job.requested_by_user_id)
            from_number = caller_id or telnyx_outbound_caller_id(config)
            res = TelnyxVoiceAdapter.start_outbound_call(
                to_number=patient.phone_e164,
                from_number=from_number,
                config={**config, "api_key": config.get("api_key")},
                client_state={
                    "org_id": job.org_id,
                    "appointment_id": job.appointment_id,
                    "patient_id": appt.patient_id,
                    "recovery_job_id": job.id,
                },
            )
            if res.ok and res.external_id:
                job.provider = "telnyx"
                job.provider_ref = res.external_id
                job.provider_status = res.status
                job.state = "calling"
                db.add(
                    CallLog(
                        org_id=job.org_id,
                        appointment_id=job.appointment_id,
                        patient_id=appt.patient_id,
                        provider="telnyx",
                        external_call_id=res.external_id,
                        direction="outbound",
                        status=res.status,
                        to_number=patient.phone_e164,
                        from_number=from_number,
                    )
                )
                RecoveryStateMachine.transition(db, appointment=appt, to_state="calling")
            else:
                wa = TelnyxMessagingService.send_survey_message(
                    db,
                    org_id=job.org_id,
                    to_number=patient.phone_e164,
                    body="VOXBULK: we noticed you may have availability to reschedule. Reply to confirm.",
                    prefer_whatsapp=True,
                )
                if wa.ok and wa.external_id:
                    job.provider = "telnyx_whatsapp" if wa.channel == "whatsapp" else "telnyx_sms"
                    job.provider_ref = wa.external_id
                    job.provider_status = wa.status
                    job.state = "messaged"
                    db.add(
                        WhatsAppLog(
                            org_id=job.org_id,
                            appointment_id=job.appointment_id,
                            patient_id=appt.patient_id,
                            provider="telnyx",
                            external_message_id=wa.external_id,
                            status=wa.status,
                            direction="outbound",
                            to_number=patient.phone_e164,
                            body="VOXBULK: we noticed you may have availability to reschedule. Reply to confirm.",
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
