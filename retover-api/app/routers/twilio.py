from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import verify_twilio_signature
from app.models.appointment import Appointment
from app.models.recovery_job import RecoveryJob
from app.services.recovery_service import RecoveryStateMachine
from app.services.provider_settings import ProviderSettingsService
from app.services.twilio_service import TwilioCallerIdService, TwilioExecutionService

router = APIRouter(prefix="/twilio/webhooks", tags=["twilio-webhooks"])


async def _signed_form(request: Request) -> dict[str, str]:
    form = await request.form()
    return {k: str(v) for k, v in form.items()}


def _verify(db: Session, request: Request, form: dict[str, str]) -> None:
    sig = request.headers.get("X-Twilio-Signature")
    if not sig:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Twilio signature")
    auth_token = get_settings().twilio_auth_token
    try:
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="twilio")
        if enabled and isinstance(cfg, dict) and str(cfg.get("auth_token") or "").strip():
            auth_token = str(cfg["auth_token"]).strip()
    except Exception:
        pass
    if not verify_twilio_signature(auth_token=auth_token, url=str(request.url), params=form, signature=sig):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Twilio signature")


def _org_from(form: dict[str, str], header_org_id: str | None) -> str | None:
    return (
        (header_org_id or "").strip()
        or str(form.get("org_id") or "").strip()
        or str(form.get("organisation_id") or "").strip()
        or str(form.get("retover_org_id") or "").strip()
        or None
    )


@router.post("/whatsapp")
async def whatsapp_sandbox_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_retover_org_id: str | None = Header(default=None, alias="X-Retover-Org-Id"),
):
    """
    Twilio Console WhatsApp Sandbox webhook.

    Configure sandbox inbound URL to POST here. Include X-Retover-Org-Id in local
    tunnel tooling, or include org_id/retover_org_id as a form parameter when testing.
    """
    form = await _signed_form(request)
    _verify(db, request, form)
    org_id = _org_from(form, x_retover_org_id)
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing tenant org_id for WhatsApp webhook")
    log = TwilioExecutionService.log_inbound_whatsapp(db, org_id=org_id, form=form)
    return {"ok": True, "log_id": log.id}


@router.post("/calls")
async def calls_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_retover_org_id: str | None = Header(default=None, alias="X-Retover-Org-Id"),
):
    """Twilio voice webhook/statusCallback endpoint."""
    form = await _signed_form(request)
    _verify(db, request, form)
    org_id = _org_from(form, x_retover_org_id)
    log = TwilioExecutionService.log_call_webhook(db, org_id=org_id, form=form)

    call_sid = form.get("CallSid")
    call_status = form.get("CallStatus") or form.get("Status")
    if call_sid:
        job = db.execute(select(RecoveryJob).where(RecoveryJob.provider == "twilio", RecoveryJob.provider_ref == call_sid)).scalar_one_or_none()
        if job is not None:
            job.provider_status = call_status or job.provider_status
            appt = db.execute(select(Appointment).where(Appointment.id == job.appointment_id, Appointment.org_id == job.org_id)).scalar_one_or_none()
            terminal_error = None
            target = None
            if call_status in {"queued", "initiated", "ringing", "in-progress", "answered"}:
                target = "calling"
            elif call_status == "completed":
                target = "messaged"
            elif call_status in {"busy", "no-answer", "failed", "canceled"}:
                target = "failed"
                terminal_error = f"Twilio: {call_status}"
            if target:
                job.state = target
                if terminal_error:
                    job.last_error = terminal_error
                if appt is not None:
                    try:
                        RecoveryStateMachine.transition(db, appointment=appt, to_state=target, error=terminal_error)
                    except ValueError:
                        pass
            db.add(job)
            db.commit()

    return {"ok": True, "log_id": log.id if log else None}


@router.post("/caller-id")
async def caller_id_verification_webhook(request: Request, db: Session = Depends(get_db)):
    """Twilio Outgoing Caller ID verification status callback."""
    form = await _signed_form(request)
    _verify(db, request, form)
    user = TwilioCallerIdService.mark_callback(db, form=form)
    return {"ok": True, "user_id": user.id if user else None}
