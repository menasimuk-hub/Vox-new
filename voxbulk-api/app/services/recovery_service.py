from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.branch import Branch
from app.models.organisation import Organisation
from app.models.patient import Patient
from app.models.webhook_event import WebhookEvent
from app.models.recovery_job import RecoveryJob
from app.models.appointment import Appointment


class OrganisationService:
    @staticmethod
    def get_org(db: Session, org_id: str) -> Organisation | None:
        return db.execute(select(Organisation).where(Organisation.id == org_id)).scalar_one_or_none()

    @staticmethod
    def update_org_name(db: Session, org_id: str, name: str) -> Organisation:
        org = db.execute(select(Organisation).where(Organisation.id == org_id)).scalar_one()
        org.name = name
        db.add(org)
        db.commit()
        db.refresh(org)
        return org

    @staticmethod
    def update_org_profile(db: Session, org_id: str, **fields) -> Organisation:
        org = db.execute(select(Organisation).where(Organisation.id == org_id)).scalar_one()
        if "name" in fields and fields["name"] is not None:
            name = str(fields["name"]).strip()
            if name:
                org.name = name
        for field in [
            "address_line1",
            "address_line2",
            "city",
            "county_state",
            "postcode",
            "country",
            "contact_name",
            "contact_email",
            "contact_phone",
            "website",
        ]:
            if field in fields:
                raw = fields.get(field)
                setattr(org, field, str(raw).strip() if raw is not None and str(raw).strip() else None)
        if "enabled_services" in fields and fields["enabled_services"] is not None:
            from app.services.org_enabled_services import serialize_enabled_services

            org.enabled_services_json = serialize_enabled_services(fields["enabled_services"])
        db.add(org)
        db.commit()
        db.refresh(org)
        return org


class BranchService:
    @staticmethod
    def list_branches(db: Session, org_id: str) -> list[Branch]:
        return list(db.execute(select(Branch).where(Branch.org_id == org_id).order_by(Branch.created_at.desc())).scalars())

    @staticmethod
    def create_branch(db: Session, org_id: str, *, name: str, address_line1: str | None, city: str | None, postcode: str | None) -> Branch:
        branch = Branch(org_id=org_id, name=name, address_line1=address_line1, city=city, postcode=postcode)
        db.add(branch)
        db.commit()
        db.refresh(branch)
        return branch


class PatientService:
    @staticmethod
    def _validate_branch(db: Session, org_id: str, branch_id: str) -> None:
        ok = db.execute(select(Branch.id).where(Branch.id == branch_id, Branch.org_id == org_id)).scalar_one_or_none()
        if ok is None:
            raise ValueError("Invalid branch_id for tenant")

    @staticmethod
    def list_patients(db: Session, org_id: str) -> list[Patient]:
        return list(db.execute(select(Patient).where(Patient.org_id == org_id).order_by(Patient.created_at.desc())).scalars())

    @staticmethod
    def get_patient(db: Session, org_id: str, patient_id: str) -> Patient | None:
        return db.execute(select(Patient).where(Patient.id == patient_id, Patient.org_id == org_id)).scalar_one_or_none()

    @staticmethod
    def create_patient(db: Session, org_id: str, **kwargs) -> Patient:
        branch_id = kwargs.get("branch_id")
        if branch_id:
            PatientService._validate_branch(db, org_id, branch_id)
        obj = Patient(org_id=org_id, **kwargs)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj


class WebhookEventService:
    @staticmethod
    def extract_external_event_id(provider: str, raw_body: bytes) -> str | None:
        if provider == "twilio":
            try:
                from urllib.parse import parse_qs

                parsed = parse_qs(raw_body.decode("utf-8"), keep_blank_values=True)
                call_sid = (parsed.get("CallSid") or [None])[0]
                call_status = (parsed.get("CallStatus") or [None])[0]
                if call_sid and call_status:
                    return f"{call_sid}:{call_status}"
                msg_sid = (parsed.get("MessageSid") or [None])[0]
                msg_status = (parsed.get("MessageStatus") or [None])[0]
                if msg_sid and msg_status:
                    return f"{msg_sid}:{msg_status}"
                return call_sid or msg_sid
            except Exception:
                return None
        if provider == "gocardless":
            try:
                data = json.loads(raw_body.decode("utf-8"))
                events = data.get("events") or []
                ids = [str(e.get("id")) for e in events if isinstance(e, dict) and e.get("id")]
                if not ids:
                    return None
                if len(ids) == 1:
                    return ids[0]
                # batch delivery: stable fingerprint of ids
                return hashlib.sha256((",".join(sorted(ids))).encode("utf-8")).hexdigest()
            except Exception:
                return None
        return None
    @staticmethod
    def _dedupe_key(provider: str, raw_body: bytes, external_event_id: str | None) -> str:
        # Prefer provider's external id if available; otherwise hash payload.
        if external_event_id:
            return external_event_id
        return hashlib.sha256(raw_body).hexdigest()

    @staticmethod
    def persist_received(
        db: Session,
        *,
        provider: str,
        raw_body: bytes,
        org_id: str | None = None,
        external_event_id: str | None = None,
        signature_valid: bool = True,
    ) -> tuple[WebhookEvent, bool]:
        dedupe_key = WebhookEventService._dedupe_key(provider, raw_body, external_event_id)
        obj = WebhookEvent(
            provider=provider,
            external_event_id=external_event_id,
            dedupe_key=dedupe_key,
            org_id=org_id,
            signature_valid=signature_valid,
            status="received",
            attempts=0,
            raw_body=raw_body.decode("utf-8", errors="replace"),
        )
        db.add(obj)
        try:
            db.commit()
            db.refresh(obj)
            return obj, True
        except IntegrityError:
            db.rollback()
            existing = db.execute(
                select(WebhookEvent).where(WebhookEvent.provider == provider, WebhookEvent.dedupe_key == dedupe_key)
            ).scalar_one()
            return existing, False

    @staticmethod
    def mark_processed(db: Session, event_id: int) -> None:
        obj = db.execute(select(WebhookEvent).where(WebhookEvent.id == event_id)).scalar_one()
        obj.status = "processed"
        obj.processed_at = datetime.utcnow()
        db.add(obj)
        db.commit()

    @staticmethod
    def mark_processing(db: Session, event_id: int) -> None:
        obj = db.execute(select(WebhookEvent).where(WebhookEvent.id == event_id)).scalar_one()
        obj.status = "processing"
        obj.attempts += 1
        obj.last_error = None
        db.add(obj)
        db.commit()

    @staticmethod
    def mark_failed(db: Session, event_id: int, error: str) -> None:
        obj = db.execute(select(WebhookEvent).where(WebhookEvent.id == event_id)).scalar_one()
        obj.status = "failed"
        obj.last_error = str(error or "Webhook processing failed")[:500]
        db.add(obj)
        db.commit()


class RecoveryJobService:
    @staticmethod
    def enqueue_for_appointment(db: Session, *, org_id: str, appointment_id: str, requested_by_user_id: str | None = None) -> RecoveryJob:
        # Validate appointment belongs to tenant
        appt = db.execute(
            select(Appointment).where(Appointment.id == appointment_id, Appointment.org_id == org_id)
        ).scalar_one_or_none()
        if appt is None:
            raise ValueError("Appointment not found for tenant")

        # Move appointment into queued state (explicit transition)
        if appt.recovery_state == "pending":
            RecoveryStateMachine.transition(db, appointment=appt, to_state="queued")

        idempotency_key = f"appointment:{appointment_id}"
        obj = RecoveryJob(
            org_id=org_id,
            appointment_id=appointment_id,
            requested_by_user_id=requested_by_user_id,
            idempotency_key=idempotency_key,
            state="queued",
        )
        db.add(obj)
        try:
            db.commit()
            db.refresh(obj)
            return obj
        except IntegrityError:
            db.rollback()
            existing = db.execute(
                select(RecoveryJob).where(RecoveryJob.org_id == org_id, RecoveryJob.idempotency_key == idempotency_key)
            ).scalar_one()
            if requested_by_user_id and not existing.requested_by_user_id:
                existing.requested_by_user_id = requested_by_user_id
                db.add(existing)
                db.commit()
                db.refresh(existing)
            return existing

    @staticmethod
    def get_job(db: Session, *, org_id: str, job_id: str) -> RecoveryJob | None:
        return db.execute(select(RecoveryJob).where(RecoveryJob.id == job_id, RecoveryJob.org_id == org_id)).scalar_one_or_none()


class RecoveryStateMachine:
    STATES = {"pending", "queued", "calling", "messaged", "recovered", "failed", "skipped"}
    TERMINAL = {"recovered", "failed", "skipped"}

    # allowed transitions (explicit & safe)
    ALLOWED: dict[str, set[str]] = {
        "pending": {"queued", "skipped"},
        "queued": {"calling", "failed", "skipped"},
        "calling": {"messaged", "failed", "skipped"},
        "messaged": {"recovered", "failed"},
        "recovered": set(),
        "failed": set(),
        "skipped": set(),
    }

    @staticmethod
    def transition(db: Session, *, appointment: Appointment, to_state: str, error: str | None = None) -> None:
        if to_state not in RecoveryStateMachine.STATES:
            raise ValueError("Invalid recovery state")
        from_state = appointment.recovery_state
        if to_state == from_state:
            return
        if to_state not in RecoveryStateMachine.ALLOWED.get(from_state, set()):
            raise ValueError(f"Invalid recovery transition {from_state} -> {to_state}")
        appointment.recovery_state = to_state
        appointment.recovery_updated_at = datetime.utcnow()
        if error is not None:
            appointment.recovery_last_error = error
        db.add(appointment)

