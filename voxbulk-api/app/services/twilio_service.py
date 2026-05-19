from __future__ import annotations

from dataclasses import dataclass
import json
from urllib.parse import urlencode

import httpx

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.appointment import Appointment
from app.models.branch import Branch
from app.models.call_log import CallLog
from app.models.patient import Patient
from app.models.user import User
from app.models.whatsapp_log import WhatsAppLog
from app.services.provider_settings import ProviderSettingsService


class LogService:
    @staticmethod
    def _validate_optional_relations(db: Session, org_id: str, *, appointment_id: str | None, patient_id: str | None) -> None:
        if appointment_id:
            ok = db.execute(
                select(Appointment.id).where(Appointment.id == appointment_id, Appointment.org_id == org_id)
            ).scalar_one_or_none()
            if ok is None:
                raise ValueError("Invalid appointment_id for tenant")
        if patient_id:
            ok = db.execute(select(Patient.id).where(Patient.id == patient_id, Patient.org_id == org_id)).scalar_one_or_none()
            if ok is None:
                raise ValueError("Invalid patient_id for tenant")

    @staticmethod
    def list_call_logs(db: Session, org_id: str) -> list[CallLog]:
        rows = db.execute(
            select(
                CallLog,
                Patient.first_name,
                Patient.last_name,
                Branch.name,
                Appointment.scheduled_start,
            )
            .outerjoin(Patient, Patient.id == CallLog.patient_id)
            .outerjoin(Appointment, Appointment.id == CallLog.appointment_id)
            .outerjoin(Branch, Branch.id == Appointment.branch_id)
            .where(CallLog.org_id == org_id)
            .order_by(CallLog.id.desc())
            .limit(200)
        ).all()

        out: list[dict] = []
        for log, p_first, p_last, branch_name, appt_start in rows:
            patient_name = None
            if p_first or p_last:
                patient_name = f"{p_first or ''} {p_last or ''}".strip() or None
            out.append(
                {
                    "id": log.id,
                    "org_id": log.org_id,
                    "user_id": log.user_id,
                    "appointment_id": log.appointment_id,
                    "patient_id": log.patient_id,
                    "patient_name": patient_name,
                    "branch_name": branch_name,
                    "appointment_scheduled_start": appt_start,
                    "provider": log.provider,
                    "external_call_id": log.external_call_id,
                    "direction": log.direction,
                    "status": log.status,
                    "to_number": log.to_number,
                    "from_number": log.from_number,
                    "recording_url": log.recording_url,
                    "media_stream_id": log.media_stream_id,
                    "llm_prompt": log.llm_prompt,
                    "llm_response": log.llm_response,
                    "transcript_text": log.transcript_text,
                    "raw_payload": log.raw_payload,
                    "created_at": log.created_at,
                    "started_at": log.started_at,
                    "answered_at": log.answered_at,
                    "ended_at": log.ended_at,
                    "last_status_at": log.last_status_at,
                }
            )
        return out  # type: ignore[return-value]

    @staticmethod
    def create_call_log(db: Session, org_id: str, **kwargs) -> CallLog:
        LogService._validate_optional_relations(
            db, org_id, appointment_id=kwargs.get("appointment_id"), patient_id=kwargs.get("patient_id")
        )
        obj = CallLog(org_id=org_id, **kwargs)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    @staticmethod
    def get_call_log(db: Session, org_id: str, log_id: int) -> CallLog | None:
        return db.execute(select(CallLog).where(CallLog.id == log_id, CallLog.org_id == org_id)).scalar_one_or_none()

    @staticmethod
    def list_whatsapp_logs(db: Session, org_id: str) -> list[WhatsAppLog]:
        rows = db.execute(
            select(
                WhatsAppLog,
                Patient.first_name,
                Patient.last_name,
                Branch.name,
                Appointment.scheduled_start,
            )
            .outerjoin(Patient, Patient.id == WhatsAppLog.patient_id)
            .outerjoin(Appointment, Appointment.id == WhatsAppLog.appointment_id)
            .outerjoin(Branch, Branch.id == Appointment.branch_id)
            .where(WhatsAppLog.org_id == org_id)
            .order_by(WhatsAppLog.id.desc())
            .limit(200)
        ).all()

        out: list[dict] = []
        for log, p_first, p_last, branch_name, appt_start in rows:
            patient_name = None
            if p_first or p_last:
                patient_name = f"{p_first or ''} {p_last or ''}".strip() or None
            out.append(
                {
                    "id": log.id,
                    "org_id": log.org_id,
                    "appointment_id": log.appointment_id,
                    "patient_id": log.patient_id,
                    "patient_name": patient_name,
                    "branch_name": branch_name,
                    "appointment_scheduled_start": appt_start,
                    "provider": log.provider,
                    "external_message_id": log.external_message_id,
                    "status": log.status,
                    "direction": log.direction,
                    "to_number": log.to_number,
                    "from_number": log.from_number,
                    "body": log.body,
                    "media_json": log.media_json,
                    "raw_payload": log.raw_payload,
                    "created_at": log.created_at,
                }
            )
        return out  # type: ignore[return-value]

    @staticmethod
    def create_whatsapp_log(db: Session, org_id: str, **kwargs) -> WhatsAppLog:
        LogService._validate_optional_relations(
            db, org_id, appointment_id=kwargs.get("appointment_id"), patient_id=kwargs.get("patient_id")
        )
        obj = WhatsAppLog(org_id=org_id, **kwargs)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    @staticmethod
    def get_whatsapp_log(db: Session, org_id: str, log_id: int) -> WhatsAppLog | None:
        return db.execute(select(WhatsAppLog).where(WhatsAppLog.id == log_id, WhatsAppLog.org_id == org_id)).scalar_one_or_none()


@dataclass(frozen=True)
class ProviderResult:
    ok: bool
    status: str
    detail: str | None = None
    external_id: str | None = None


def _twilio_config(db: Session | None = None) -> dict:
    cfg: dict = {}
    if db is not None:
        try:
            row, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="twilio")
            if enabled and isinstance(row, dict):
                cfg.update(row)
        except Exception:
            cfg = {}
    s = get_settings()
    return {
        "account_sid": cfg.get("account_sid") or s.twilio_account_sid,
        "auth_token": cfg.get("auth_token") or s.twilio_auth_token,
        "api_key": cfg.get("api_key") or s.twilio_api_key,
        "api_secret": cfg.get("api_secret") or s.twilio_api_secret,
        "from_number": cfg.get("from_number") or cfg.get("voice_from") or s.twilio_from_number,
        "twiml_url": cfg.get("twiml_url") or s.twilio_twiml_url,
        "whatsapp_from": cfg.get("whatsapp_from") or cfg.get("whatsapp_sandbox_number") or s.twilio_whatsapp_from,
        "voice_webhook_url": cfg.get("voice_webhook_url"),
        "status_callback_url": cfg.get("status_callback_url"),
        "whatsapp_webhook_url": cfg.get("whatsapp_webhook_url"),
        "sandbox_mode": bool(cfg.get("sandbox_mode", True)),
    }


def _twilio_auth(config: dict) -> tuple[str, str]:
    if config.get("api_key") and config.get("api_secret"):
        return str(config["api_key"]), str(config["api_secret"])
    return str(config.get("account_sid") or ""), str(config.get("auth_token") or "")


def normalize_e164(raw: str) -> str:
    phone = "".join(ch for ch in str(raw or "").strip() if ch.isdigit() or ch == "+")
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if not phone.startswith("+") and phone.isdigit():
        phone = f"+{phone}"
    digits = phone[1:] if phone.startswith("+") else phone
    if not phone.startswith("+") or not digits.isdigit() or not (8 <= len(digits) <= 15):
        raise ValueError("Phone number must be in E.164 format, for example +447700900123")
    return phone


class TwilioAdapter:
    """
    Legacy provider adapter.

    Twilio remains available for historical WhatsApp/call logs and webhook
    compatibility. New active outbound voice calls use the Telnyx voice stack.
    """

    @staticmethod
    def is_configured(config: dict | None = None) -> bool:
        s = get_settings()
        cfg = config or {}
        return bool(
            (cfg.get("account_sid") or s.twilio_account_sid)
            and ((cfg.get("auth_token") or s.twilio_auth_token) or ((cfg.get("api_key") or s.twilio_api_key) and (cfg.get("api_secret") or s.twilio_api_secret)))
            and (cfg.get("from_number") or s.twilio_from_number)
            and (cfg.get("twiml_url") or s.twilio_twiml_url)
        )

    @staticmethod
    def _create_call(
        *,
        account_sid: str,
        api_key: str,
        api_secret: str,
        to_number: str,
        from_number: str,
        twiml_url: str,
        status_callback_url: str | None = None,
    ) -> dict:
        """
        Real Twilio REST API call initiation.

        This method performs the network request and is separated to allow deterministic tests via monkeypatching.
        """
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"
        auth = (api_key, api_secret)
        data = {"To": to_number, "From": from_number, "Url": twiml_url}
        if status_callback_url:
            data["StatusCallback"] = status_callback_url
            data["StatusCallbackEvent"] = "initiated ringing answered completed"
            data["StatusCallbackMethod"] = "POST"
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, data=data, auth=auth)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def start_outbound_call(*, to_number: str, from_number: str | None = None, config: dict | None = None) -> ProviderResult:
        # Ensure tests/runtime env changes are respected.
        get_settings.cache_clear()
        if not TwilioAdapter.is_configured(config):
            return ProviderResult(ok=False, status="not_configured", detail="Twilio API credentials missing")

        s = get_settings()
        cfg = config or {}
        account_sid = cfg.get("account_sid") or s.twilio_account_sid
        auth_user, auth_secret = _twilio_auth({**cfg, "account_sid": account_sid})
        twiml_url = cfg.get("twiml_url") or s.twilio_twiml_url
        from_num = from_number or (cfg.get("from_number") or s.twilio_from_number)
        try:
            payload = TwilioAdapter._create_call(
                account_sid=account_sid,
                api_key=auth_user,
                api_secret=auth_secret,
                to_number=to_number,
                from_number=from_num,
                twiml_url=twiml_url,
                status_callback_url=cfg.get("status_callback_url"),
            )
            call_sid = payload.get("sid") or payload.get("call_sid")
            if not call_sid:
                return ProviderResult(ok=False, status="unexpected_response", detail="Missing CallSid in Twilio response")
            return ProviderResult(ok=True, status="queued", external_id=str(call_sid))
        except httpx.HTTPError as e:
            return ProviderResult(ok=False, status="http_error", detail=str(e))
        except Exception as e:
            return ProviderResult(ok=False, status="error", detail=str(e))


class TwilioCallerIdService:
    @staticmethod
    def _create_validation_request(
        *,
        account_sid: str,
        auth_user: str,
        auth_secret: str,
        phone_number: str,
        friendly_name: str,
        status_callback_url: str | None = None,
    ) -> dict:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/OutgoingCallerIds.json"
        data = {"PhoneNumber": phone_number, "FriendlyName": friendly_name}
        if status_callback_url:
            data["StatusCallback"] = status_callback_url
            data["StatusCallbackMethod"] = "POST"
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, data=data, auth=(auth_user, auth_secret))
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _list_outgoing_caller_ids(*, account_sid: str, auth_user: str, auth_secret: str, phone_number: str) -> dict:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/OutgoingCallerIds.json"
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, params={"PhoneNumber": phone_number}, auth=(auth_user, auth_secret))
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def phone_status(user: User) -> dict:
        return {
            "phone_number": user.phone_number,
            "phone_e164": user.phone_e164,
            "verification_status": user.phone_verification_status or "unverified",
            "twilio_outgoing_caller_id_sid": user.twilio_outgoing_caller_id_sid,
            "twilio_phone_verification_sid": user.twilio_phone_verification_sid,
            "verification_requested_at": user.phone_verification_requested_at,
            "verification_completed_at": user.phone_verification_completed_at,
            "last_error": user.phone_verification_last_error,
        }

    @staticmethod
    def save_phone(db: Session, *, user: User, phone_number: str) -> User:
        normalized = normalize_e164(phone_number)
        if user.phone_e164 != normalized:
            user.phone_number = phone_number.strip()
            user.phone_e164 = normalized
            user.phone_verification_status = "unverified"
            user.twilio_outgoing_caller_id_sid = None
            user.twilio_phone_verification_sid = None
            user.phone_verification_requested_at = None
            user.phone_verification_completed_at = None
            user.phone_verification_last_error = None
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def start_verification(db: Session, *, user: User) -> dict:
        if not user.phone_e164:
            raise ValueError("Save a phone number before starting verification")
        config = _twilio_config(db)
        account_sid = str(config.get("account_sid") or "")
        auth_user, auth_secret = _twilio_auth(config)
        if not account_sid or not auth_secret:
            raise ValueError("Twilio Account SID/Auth Token are not configured by admin")
        callback = config.get("caller_id_status_callback_url") or config.get("status_callback_url")
        try:
            payload = TwilioCallerIdService._create_validation_request(
                account_sid=account_sid,
                auth_user=auth_user,
                auth_secret=auth_secret,
                phone_number=user.phone_e164,
                friendly_name=f"VOXBULK user {user.email}",
                status_callback_url=callback,
            )
        except httpx.HTTPError as e:
            user.phone_verification_status = "failed"
            user.phone_verification_last_error = str(e)[:500]
            db.add(user)
            db.commit()
            raise ValueError(f"Twilio verification request failed: {e}") from e

        from datetime import datetime

        user.phone_verification_status = "pending"
        user.phone_verification_requested_at = datetime.utcnow()
        user.phone_verification_completed_at = None
        user.phone_verification_last_error = None
        user.twilio_phone_verification_sid = str(payload.get("call_sid") or payload.get("sid") or "") or None
        if payload.get("sid") and str(payload.get("sid")).startswith("PN"):
            user.twilio_outgoing_caller_id_sid = str(payload["sid"])
        db.add(user)
        db.commit()
        db.refresh(user)
        return {
            "status": "pending",
            "validation_code": payload.get("validation_code"),
            "verification_sid": user.twilio_phone_verification_sid,
            "outgoing_caller_id_sid": user.twilio_outgoing_caller_id_sid,
        }

    @staticmethod
    def refresh_verification(db: Session, *, user: User) -> User:
        if not user.phone_e164:
            return user
        config = _twilio_config(db)
        account_sid = str(config.get("account_sid") or "")
        auth_user, auth_secret = _twilio_auth(config)
        if not account_sid or not auth_secret:
            raise ValueError("Twilio Account SID/Auth Token are not configured by admin")
        payload = TwilioCallerIdService._list_outgoing_caller_ids(
            account_sid=account_sid,
            auth_user=auth_user,
            auth_secret=auth_secret,
            phone_number=user.phone_e164,
        )
        rows = payload.get("outgoing_caller_ids") or payload.get("outgoing_callerids") or []
        if rows:
            from datetime import datetime

            row = rows[0]
            user.phone_verification_status = "verified"
            user.twilio_outgoing_caller_id_sid = str(row.get("sid") or user.twilio_outgoing_caller_id_sid or "")
            user.phone_verification_completed_at = datetime.utcnow()
            user.phone_verification_last_error = None
            db.add(user)
            db.commit()
            db.refresh(user)
        return user

    @staticmethod
    def mark_callback(db: Session, *, form: dict[str, str]) -> User | None:
        phone = form.get("PhoneNumber") or form.get("Called") or form.get("To")
        call_sid = form.get("CallSid")
        user = None
        if call_sid:
            user = db.execute(select(User).where(User.twilio_phone_verification_sid == call_sid)).scalar_one_or_none()
        if user is None and phone:
            try:
                phone_e164 = normalize_e164(phone)
                user = db.execute(select(User).where(User.phone_e164 == phone_e164)).scalar_one_or_none()
            except ValueError:
                user = None
        if user is None:
            return None

        from datetime import datetime

        status = (form.get("VerificationStatus") or form.get("CallStatus") or form.get("Status") or "").lower()
        if status in {"verified", "completed", "approved"}:
            user.phone_verification_status = "verified"
            user.phone_verification_completed_at = datetime.utcnow()
            if form.get("OutgoingCallerIdSid"):
                user.twilio_outgoing_caller_id_sid = form.get("OutgoingCallerIdSid")
            user.phone_verification_last_error = None
        elif status in {"failed", "busy", "no-answer", "canceled", "cancelled"}:
            user.phone_verification_status = "failed"
            user.phone_verification_last_error = f"Twilio verification call status: {status}"
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def verified_caller_id_for_user(db: Session, *, user_id: str | None) -> str | None:
        if not user_id:
            return None
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user and user.phone_e164 and user.phone_verification_status == "verified" and user.twilio_outgoing_caller_id_sid:
            return user.phone_e164
        return None


class TwilioWhatsAppAdapter:
    @staticmethod
    def is_configured(config: dict | None = None) -> bool:
        s = get_settings()
        cfg = config or {}
        return bool(
            (cfg.get("account_sid") or s.twilio_account_sid)
            and ((cfg.get("auth_token") or s.twilio_auth_token) or ((cfg.get("api_key") or s.twilio_api_key) and (cfg.get("api_secret") or s.twilio_api_secret)))
            and (cfg.get("whatsapp_from") or s.twilio_whatsapp_from)
        )

    @staticmethod
    def _create_message(
        *,
        account_sid: str,
        api_key: str,
        api_secret: str,
        to_number: str,
        from_number: str,
        body: str,
        media_urls: list[str] | None = None,
    ) -> dict:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        auth = (api_key, api_secret)
        data = {"To": f"whatsapp:{to_number}" if not str(to_number).startswith("whatsapp:") else str(to_number), "From": from_number, "Body": body}
        for media_url in media_urls or []:
            data.setdefault("MediaUrl", [])
            data["MediaUrl"].append(str(media_url))
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, data=data, auth=auth)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def send_message(*, to_number: str, body: str, media_urls: list[str] | None = None, config: dict | None = None) -> ProviderResult:
        get_settings.cache_clear()
        if not TwilioWhatsAppAdapter.is_configured(config):
            return ProviderResult(ok=False, status="not_configured", detail="Twilio WhatsApp config missing")
        s = get_settings()
        cfg = config or {}
        account_sid = cfg.get("account_sid") or s.twilio_account_sid
        auth_user, auth_secret = _twilio_auth({**cfg, "account_sid": account_sid})
        whatsapp_from = cfg.get("whatsapp_from") or s.twilio_whatsapp_from
        try:
            payload = TwilioWhatsAppAdapter._create_message(
                account_sid=account_sid,
                api_key=auth_user,
                api_secret=auth_secret,
                to_number=to_number,
                from_number=whatsapp_from,
                body=body,
                media_urls=media_urls,
            )
            sid = payload.get("sid") or payload.get("message_sid")
            if not sid:
                return ProviderResult(ok=False, status="unexpected_response", detail="Missing MessageSid in Twilio response")
            return ProviderResult(ok=True, status=str(payload.get("status") or "queued"), external_id=str(sid))
        except httpx.HTTPError as e:
            return ProviderResult(ok=False, status="http_error", detail=str(e))
        except Exception as e:
            return ProviderResult(ok=False, status="error", detail=str(e))


class TwilioExecutionService:
    @staticmethod
    def send_whatsapp(
        db: Session,
        *,
        org_id: str,
        to_number: str,
        body: str,
        appointment_id: str | None = None,
        patient_id: str | None = None,
        media_urls: list[str] | None = None,
    ) -> WhatsAppLog:
        LogService._validate_optional_relations(db, org_id, appointment_id=appointment_id, patient_id=patient_id)
        config = _twilio_config(db)
        result = TwilioWhatsAppAdapter.send_message(to_number=to_number, body=body, media_urls=media_urls, config=config)
        log = WhatsAppLog(
            org_id=org_id,
            appointment_id=appointment_id,
            patient_id=patient_id,
            provider="twilio",
            external_message_id=result.external_id,
            status=result.status if result.ok else "failed",
            direction="outbound",
            to_number=to_number,
            from_number=config.get("whatsapp_from"),
            body=body,
            media_json=json.dumps(media_urls or []),
            raw_payload=json.dumps({"ok": result.ok, "status": result.status, "detail": result.detail, "sandbox": config.get("sandbox_mode")}),
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def start_call(
        db: Session,
        *,
        org_id: str,
        to_number: str,
        appointment_id: str | None = None,
        patient_id: str | None = None,
        user_id: str | None = None,
    ) -> CallLog:
        LogService._validate_optional_relations(db, org_id, appointment_id=appointment_id, patient_id=patient_id)
        config = _twilio_config(db)
        caller_id = TwilioCallerIdService.verified_caller_id_for_user(db, user_id=user_id) or config.get("from_number")
        result = TwilioAdapter.start_outbound_call(to_number=to_number, from_number=caller_id, config=config)
        log = CallLog(
            org_id=org_id,
            appointment_id=appointment_id,
            patient_id=patient_id,
            provider="twilio",
            external_call_id=result.external_id,
            direction="outbound",
            status=result.status if result.ok else "failed",
            to_number=to_number,
            from_number=caller_id,
            raw_payload=json.dumps({"ok": result.ok, "status": result.status, "detail": result.detail, "sandbox": config.get("sandbox_mode"), "caller_id_source": "verified_user" if caller_id != config.get("from_number") else "default"}),
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def log_inbound_whatsapp(db: Session, *, org_id: str, form: dict[str, str]) -> WhatsAppLog:
        num_media = int(form.get("NumMedia") or 0)
        media = []
        for i in range(num_media):
            media.append({"url": form.get(f"MediaUrl{i}"), "content_type": form.get(f"MediaContentType{i}")})
        log = WhatsAppLog(
            org_id=org_id,
            provider="twilio",
            external_message_id=form.get("MessageSid") or form.get("SmsSid"),
            status=form.get("SmsStatus") or form.get("MessageStatus") or "received",
            direction="inbound",
            to_number=form.get("To"),
            from_number=form.get("From"),
            body=form.get("Body"),
            media_json=json.dumps(media),
            raw_payload=json.dumps(form, ensure_ascii=False),
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def log_call_webhook(db: Session, *, org_id: str | None, form: dict[str, str]) -> CallLog | None:
        call_sid = form.get("CallSid")
        if not call_sid:
            return None
        log = db.execute(select(CallLog).where(CallLog.external_call_id == call_sid)).scalar_one_or_none()
        if log is None:
            if not org_id:
                return None
            log = CallLog(
                org_id=org_id,
                provider="twilio",
                external_call_id=call_sid,
                direction="inbound" if str(form.get("Direction") or "").startswith("inbound") else "outbound",
            )
        log.status = form.get("CallStatus") or form.get("Status") or log.status
        log.to_number = form.get("To") or log.to_number
        log.from_number = form.get("From") or log.from_number
        log.recording_url = form.get("RecordingUrl") or log.recording_url
        log.raw_payload = json.dumps(form, ensure_ascii=False)
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

