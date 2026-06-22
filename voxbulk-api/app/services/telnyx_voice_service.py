from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.http_ssl import httpx_ssl_verify
from app.models.call_log import CallLog
from app.models.user import User
from app.services.agents.manager import AgentManager
from app.services.provider_settings import ProviderSettingsService
from app.services.telnyx_api_key import (
    normalize_telnyx_api_key,
    normalize_telnyx_e164,
    require_telnyx_api_key,
    resolve_telnyx_api_key,
    telnyx_auth_hint,
    telnyx_caller_hint,
    telnyx_outbound_caller_id,
)
from app.services.messaging_log_service import LogService, normalize_e164


@dataclass(frozen=True)
class TelnyxProviderResult:
    ok: bool
    status: str
    external_id: str | None = None
    detail: str | None = None
    payload: dict[str, Any] | None = None


class TelnyxConfigError(ValueError):
    pass


def _telnyx_config(db: Session) -> dict[str, Any]:
    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
    config = ProviderSettingsService._validate_telnyx_config(cfg or {})
    api_key, _source = resolve_telnyx_api_key(db, config)
    if not enabled or not api_key:
        raise TelnyxConfigError("Telnyx is not configured or enabled")
    return {
        **config,
        "api_key": api_key,
        "connection_id": str(config.get("connection_id") or "").strip(),
        "default_outbound_number": str(config.get("default_outbound_number") or "").strip(),
        "fallback_caller_id": telnyx_outbound_caller_id(config),
        "outbound_voice_profile_id": str(config.get("outbound_voice_profile_id") or "").strip(),
        "voice_webhook_url": str(config.get("voice_webhook_url") or "").strip(),
        "status_callback_url": str(config.get("status_callback_url") or "").strip(),
        "verified_number_webhook_url": str(config.get("verified_number_webhook_url") or "").strip(),
        "media_stream_url": str(config.get("media_stream_url") or "").strip(),
    }


TELNYX_WHATSAPP_BUSINESS_ACCOUNTS_URL = "https://api.telnyx.com/v2/whatsapp/business_accounts"


def _telnyx_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {normalize_telnyx_api_key(api_key)}", "Content-Type": "application/json", "Accept": "application/json"}


def resolve_telnyx_whatsapp_waba_id(
    db: Session,
    config: dict[str, Any] | None = None,
    *,
    template_waba_id: str | None = None,
) -> str:
    """Resolve WABA id for WhatsApp template create/sync — config, template row, then Telnyx API."""
    cfg: dict[str, Any] = dict(config or {})
    if not cfg.get("api_key"):
        try:
            cfg = {**cfg, **_telnyx_config(db)}
        except TelnyxConfigError:
            pass

    for candidate in (
        str(cfg.get("whatsapp_waba_id") or "").strip(),
        str(cfg.get("waba_id") or "").strip(),
        str(template_waba_id or "").strip(),
    ):
        if candidate:
            return candidate

    api_key = normalize_telnyx_api_key(str(cfg.get("api_key") or ""))
    if not api_key:
        try:
            api_key, _ = require_telnyx_api_key(db)
        except Exception:
            return ""

    try:
        with httpx.Client(timeout=20.0, verify=httpx_ssl_verify()) as client:
            response = client.get(
                TELNYX_WHATSAPP_BUSINESS_ACCOUNTS_URL,
                headers=_telnyx_headers(api_key),
                params={"page[size]": 50, "page[number]": 1},
            )
            response.raise_for_status()
            body = response.json()
    except Exception:
        return ""

    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, list) or not data:
        return ""

    ordered = sorted(
        [item for item in data if isinstance(item, dict)],
        key=lambda item: (
            0
            if str(item.get("status") or "").upper() in {"APPROVED", "CONNECTED", "ACTIVE", "VERIFIED"}
            else 1
        ),
    )
    for item in ordered:
        meta_waba = str(item.get("waba_id") or "").strip()
        if meta_waba:
            return meta_waba
    for item in ordered:
        internal_id = str(item.get("id") or "").strip()
        if internal_id:
            return internal_id
    return ""


def _encode_client_state(state: dict[str, Any]) -> str:
    """Telnyx requires client_state as a base64-encoded JSON string."""
    raw = json.dumps(state, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _decode_client_state(value: str) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        decoded = base64.b64decode(value, validate=True).decode("utf-8")
        parsed = json.loads(decoded)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None


def _telnyx_http_error_detail(exc: httpx.HTTPStatusError) -> str:
    detail = str(exc)
    response = exc.response
    if response is not None:
        try:
            body = response.json()
            if isinstance(body, dict):
                errors = body.get("errors")
                if isinstance(errors, list) and errors:
                    first = errors[0]
                    if isinstance(first, dict):
                        detail = str(first.get("detail") or first.get("title") or detail)
        except Exception:
            pass
        if response.status_code == 401:
            return f"Telnyx API key rejected (401 Unauthorized): {detail}"
    return detail


class TelnyxCallerIdService:
    @staticmethod
    def phone_status(user: User) -> dict[str, Any]:
        return {
            "phone_number": user.phone_number,
            "phone_e164": user.phone_e164,
            "verification_status": user.telnyx_phone_verification_status or user.phone_verification_status or "unverified",
            "telnyx_verified_number_id": user.telnyx_verified_number_id,
            "telnyx_verification_id": user.telnyx_verification_id,
            "verification_requested_at": user.telnyx_phone_verification_requested_at or user.phone_verification_requested_at,
            "verification_completed_at": user.telnyx_phone_verification_completed_at or user.phone_verification_completed_at,
            "last_error": user.telnyx_phone_verification_last_error or user.phone_verification_last_error,
        }

    @staticmethod
    def save_phone(db: Session, *, user: User, phone_number: str) -> User:
        normalized = normalize_e164(phone_number)
        if user.phone_e164 != normalized:
            user.phone_number = phone_number.strip()
            user.phone_e164 = normalized
            user.phone_verification_status = "unverified"
            user.phone_verification_requested_at = None
            user.phone_verification_completed_at = None
            user.phone_verification_last_error = None
            user.twilio_outgoing_caller_id_sid = None
            user.twilio_phone_verification_sid = None
            user.telnyx_verified_number_id = None
            user.telnyx_verification_id = None
            user.telnyx_phone_verification_status = "unverified"
            user.telnyx_phone_verification_requested_at = None
            user.telnyx_phone_verification_completed_at = None
            user.telnyx_phone_verification_last_error = None
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def _create_verified_number_request(*, api_key: str, phone_number: str, webhook_url: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"phone_number": phone_number, "verification_method": "call"}
        if webhook_url:
            payload["webhook_url"] = webhook_url
        with httpx.Client(timeout=20.0, verify=httpx_ssl_verify()) as client:
            response = client.post("https://api.telnyx.com/v2/verified_numbers", json=payload, headers=_telnyx_headers(api_key))
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _list_verified_numbers(*, api_key: str, phone_number: str) -> dict[str, Any]:
        with httpx.Client(timeout=20.0, verify=httpx_ssl_verify()) as client:
            response = client.get(
                "https://api.telnyx.com/v2/verified_numbers",
                params={"filter[phone_number]": phone_number},
                headers=_telnyx_headers(api_key),
            )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def start_verification(db: Session, *, user: User) -> dict[str, Any]:
        if not user.phone_e164:
            raise ValueError("Save a phone number before starting verification")
        config = _telnyx_config(db)
        try:
            payload = TelnyxCallerIdService._create_verified_number_request(
                api_key=config["api_key"],
                phone_number=user.phone_e164,
                webhook_url=config.get("verified_number_webhook_url"),
            )
        except httpx.HTTPError as e:
            user.telnyx_phone_verification_status = "failed"
            user.phone_verification_status = "failed"
            user.telnyx_phone_verification_last_error = str(e)[:500]
            user.phone_verification_last_error = str(e)[:500]
            db.add(user)
            db.commit()
            raise ValueError(f"Telnyx verification request failed: {e}") from e

        data = payload.get("data") or payload
        user.telnyx_phone_verification_status = str(data.get("status") or "pending").lower()
        if user.telnyx_phone_verification_status not in {"verified", "failed"}:
            user.telnyx_phone_verification_status = "pending"
        user.phone_verification_status = user.telnyx_phone_verification_status
        user.telnyx_phone_verification_requested_at = datetime.utcnow()
        user.phone_verification_requested_at = user.telnyx_phone_verification_requested_at
        user.telnyx_phone_verification_completed_at = None
        user.phone_verification_completed_at = None
        user.telnyx_phone_verification_last_error = None
        user.phone_verification_last_error = None
        user.telnyx_verification_id = str(data.get("verification_id") or data.get("id") or "") or None
        user.telnyx_verified_number_id = str(data.get("verified_number_id") or data.get("id") or "") or user.telnyx_verified_number_id
        db.add(user)
        db.commit()
        db.refresh(user)
        return {
            "status": user.telnyx_phone_verification_status,
            "verification_id": user.telnyx_verification_id,
            "verified_number_id": user.telnyx_verified_number_id,
            "verification_code": data.get("verification_code") or data.get("code"),
        }

    @staticmethod
    def refresh_verification(db: Session, *, user: User) -> User:
        if not user.phone_e164:
            return user
        config = _telnyx_config(db)
        payload = TelnyxCallerIdService._list_verified_numbers(api_key=config["api_key"], phone_number=user.phone_e164)
        rows = payload.get("data") or []
        if rows:
            TelnyxCallerIdService._apply_verified_number_payload(db, user=user, data=rows[0])
        return user

    @staticmethod
    def _apply_verified_number_payload(db: Session, *, user: User, data: dict[str, Any]) -> User:
        status = str(data.get("status") or data.get("verification_status") or "").lower()
        if status in {"verified", "success", "approved"}:
            user.telnyx_phone_verification_status = "verified"
            user.phone_verification_status = "verified"
            user.telnyx_phone_verification_completed_at = datetime.utcnow()
            user.phone_verification_completed_at = user.telnyx_phone_verification_completed_at
            user.telnyx_phone_verification_last_error = None
            user.phone_verification_last_error = None
        elif status in {"failed", "expired", "rejected", "cancelled", "canceled"}:
            user.telnyx_phone_verification_status = "failed"
            user.phone_verification_status = "failed"
            user.telnyx_phone_verification_last_error = f"Telnyx verification status: {status}"
            user.phone_verification_last_error = user.telnyx_phone_verification_last_error
        elif status:
            user.telnyx_phone_verification_status = "pending"
            user.phone_verification_status = "pending"
        user.telnyx_verified_number_id = str(data.get("verified_number_id") or data.get("id") or user.telnyx_verified_number_id or "") or None
        user.telnyx_verification_id = str(data.get("verification_id") or user.telnyx_verification_id or "") or None
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def mark_webhook(db: Session, *, payload: dict[str, Any]) -> User | None:
        data = payload.get("data") or payload
        record = data.get("payload") if isinstance(data.get("payload"), dict) else data
        phone = record.get("phone_number") or record.get("phone") or record.get("number")
        verification_id = record.get("verification_id") or record.get("id")
        verified_number_id = record.get("verified_number_id") or record.get("id")
        user = None
        if verification_id:
            user = db.execute(select(User).where(User.telnyx_verification_id == str(verification_id))).scalar_one_or_none()
        if user is None and verified_number_id:
            user = db.execute(select(User).where(User.telnyx_verified_number_id == str(verified_number_id))).scalar_one_or_none()
        if user is None and phone:
            try:
                user = db.execute(select(User).where(User.phone_e164 == normalize_e164(str(phone)))).scalar_one_or_none()
            except ValueError:
                user = None
        if user is None:
            return None
        return TelnyxCallerIdService._apply_verified_number_payload(db, user=user, data=record)

    @staticmethod
    def verified_caller_id_for_user(db: Session, *, user_id: str | None) -> str | None:
        if not user_id:
            return None
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if (
            user
            and user.phone_e164
            and user.telnyx_phone_verification_status == "verified"
            and user.telnyx_verified_number_id
        ):
            return user.phone_e164
        return None


class TelnyxVoiceAdapter:
    @staticmethod
    def list_account_phone_numbers(*, api_key: str) -> list[str]:
        with httpx.Client(timeout=20.0, verify=httpx_ssl_verify()) as client:
            response = client.get(
                "https://api.telnyx.com/v2/phone_numbers",
                headers=_telnyx_headers(api_key),
                params={"page[size]": 250},
            )
        response.raise_for_status()
        numbers: list[str] = []
        for row in (response.json().get("data") or []):
            if isinstance(row, dict):
                pn = str(row.get("phone_number") or "").strip()
                if pn:
                    numbers.append(pn)
        return numbers

    @staticmethod
    def validate_from_number(*, api_key: str, from_number: str) -> tuple[str, list[str], str | None]:
        try:
            normalized = normalize_telnyx_e164(from_number)
        except ValueError as e:
            return "", [], str(e)
        try:
            numbers = TelnyxVoiceAdapter.list_account_phone_numbers(api_key=api_key)
        except Exception:
            return normalized, [], None
        if numbers and normalized not in numbers:
            return normalized, numbers, telnyx_caller_hint(normalized, numbers)
        return normalized, numbers, None

    @staticmethod
    def _create_call(
        *,
        api_key: str,
        connection_id: str,
        to_number: str,
        from_number: str,
        voice_webhook_url: str | None = None,
        status_callback_url: str | None = None,
        media_stream_url: str | None = None,
        client_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"connection_id": connection_id, "to": to_number, "from": from_number}
        if voice_webhook_url:
            payload["webhook_url"] = voice_webhook_url
        if status_callback_url:
            payload["status_callback_url"] = status_callback_url
        if media_stream_url:
            payload["stream_url"] = media_stream_url
            payload["stream_track"] = "both_tracks"
        if client_state:
            payload["client_state"] = _encode_client_state(client_state)
        with httpx.Client(timeout=20.0, verify=httpx_ssl_verify()) as client:
            response = client.post("https://api.telnyx.com/v2/calls", json=payload, headers=_telnyx_headers(api_key))
        response.raise_for_status()
        return response.json()

    @staticmethod
    def start_outbound_call(
        *,
        to_number: str,
        from_number: str,
        config: dict[str, Any],
        client_state: dict[str, Any] | None = None,
    ) -> TelnyxProviderResult:
        connection_id = str(config.get("connection_id") or "").strip()
        api_key = normalize_telnyx_api_key(str(config.get("api_key") or ""))
        if not api_key or not connection_id or not from_number:
            return TelnyxProviderResult(ok=False, status="not_configured", detail="Telnyx API key, connection ID, and caller ID are required")
        try:
            to_e164 = normalize_telnyx_e164(to_number)
            from_e164, account_numbers, from_error = TelnyxVoiceAdapter.validate_from_number(api_key=api_key, from_number=from_number)
            if from_error:
                return TelnyxProviderResult(ok=False, status="invalid_caller_id", detail=from_error)
            payload = TelnyxVoiceAdapter._create_call(
                api_key=api_key,
                connection_id=connection_id,
                to_number=to_e164,
                from_number=from_e164,
                voice_webhook_url=config.get("voice_webhook_url"),
                status_callback_url=config.get("status_callback_url"),
                media_stream_url=config.get("media_stream_url"),
                client_state=client_state,
            )
            data = payload.get("data") or payload
            call_id = data.get("call_control_id") or data.get("call_leg_id") or data.get("id")
            return TelnyxProviderResult(ok=bool(call_id), status=str(data.get("status") or "queued"), external_id=str(call_id) if call_id else None, payload=payload)
        except httpx.HTTPStatusError as e:
            detail = _telnyx_http_error_detail(e)
            if e.response is not None and e.response.status_code == 401:
                return TelnyxProviderResult(ok=False, status="http_error", detail=f"{detail}. {telnyx_auth_hint(api_key)}")
            if "origination" in detail.lower() or ("invalid" in detail.lower() and "caller" in detail.lower()):
                return TelnyxProviderResult(ok=False, status="http_error", detail=f"{detail}. {telnyx_caller_hint(from_e164, account_numbers)}")
            return TelnyxProviderResult(ok=False, status="http_error", detail=detail)
        except httpx.HTTPError as e:
            return TelnyxProviderResult(ok=False, status="http_error", detail=str(e))
        except Exception as e:
            return TelnyxProviderResult(ok=False, status="error", detail=str(e))

    @staticmethod
    def start_ai_assistant(
        *,
        call_control_id: str,
        assistant_id: str,
        config: dict[str, Any],
        instructions: str | None = None,
        greeting: str | None = None,
        prepared: bool = False,
    ) -> TelnyxProviderResult:
        from app.services.telnyx_assistant_service import normalize_telnyx_assistant_id

        api_key = normalize_telnyx_api_key(str(config.get("api_key") or ""))
        call_id = str(call_control_id or "").strip()
        clean_assistant = normalize_telnyx_assistant_id(assistant_id)
        if not api_key or not call_id:
            return TelnyxProviderResult(
                ok=False,
                status="not_configured",
                detail="Telnyx API key and call_control_id are required",
            )
        clean_instructions = str(instructions or "").strip()
        clean_greeting = str(greeting or "").strip()
        assistant_block: dict[str, Any] = {"id": clean_assistant}
        if not prepared and clean_instructions:
            assistant_block["instructions"] = clean_instructions
        payload: dict[str, Any] = {"assistant": assistant_block}
        if clean_greeting:
            payload["greeting"] = clean_greeting
        try:
            with httpx.Client(timeout=15.0, verify=httpx_ssl_verify()) as client:
                response = client.post(
                    f"https://api.telnyx.com/v2/calls/{call_id}/actions/ai_assistant_start",
                    json=payload,
                    headers=_telnyx_headers(api_key),
                )
            response.raise_for_status()
            body = response.json()
            return TelnyxProviderResult(ok=True, status="assistant_started", external_id=call_id, payload=body)
        except httpx.HTTPStatusError as e:
            detail = _telnyx_http_error_detail(e)
            return TelnyxProviderResult(ok=False, status="http_error", detail=detail)
        except httpx.HTTPError as e:
            return TelnyxProviderResult(ok=False, status="http_error", detail=str(e))
        except Exception as e:
            return TelnyxProviderResult(ok=False, status="error", detail=str(e))

    @staticmethod
    def hangup_call(*, call_control_id: str, config: dict[str, Any]) -> TelnyxProviderResult:
        api_key = normalize_telnyx_api_key(str(config.get("api_key") or ""))
        call_id = str(call_control_id or "").strip()
        if not api_key or not call_id:
            return TelnyxProviderResult(
                ok=False,
                status="not_configured",
                detail="Telnyx API key and call_control_id are required",
            )
        try:
            with httpx.Client(timeout=20.0, verify=httpx_ssl_verify()) as client:
                response = client.post(
                    f"https://api.telnyx.com/v2/calls/{call_id}/actions/hangup",
                    json={},
                    headers=_telnyx_headers(api_key),
                )
            response.raise_for_status()
            body = response.json()
            return TelnyxProviderResult(ok=True, status="hangup_sent", external_id=call_id, payload=body)
        except httpx.HTTPStatusError as e:
            detail = _telnyx_http_error_detail(e)
            if e.response is not None and e.response.status_code == 401:
                detail = f"{detail}. {telnyx_auth_hint(api_key)}"
            return TelnyxProviderResult(ok=False, status="http_error", detail=detail)
        except httpx.HTTPError as e:
            return TelnyxProviderResult(ok=False, status="http_error", detail=str(e))
        except Exception as e:
            return TelnyxProviderResult(ok=False, status="error", detail=str(e))


class TelnyxExecutionService:
    @staticmethod
    def start_call(
        db: Session,
        *,
        org_id: str,
        to_number: str,
        appointment_id: str | None = None,
        patient_id: str | None = None,
        user_id: str | None = None,
        llm_prompt: str | None = None,
        agent_id: str | None = None,
    ) -> CallLog:
        LogService._validate_optional_relations(db, org_id, appointment_id=appointment_id, patient_id=patient_id)
        agent = AgentManager.resolve_agent(db, org_id=org_id, agent_id=agent_id)
        to_e164 = normalize_e164(to_number)
        config = _telnyx_config(db)
        verified_caller_id = TelnyxCallerIdService.verified_caller_id_for_user(db, user_id=user_id)
        from app.services.telnyx_number_routing_service import TelnyxNumberRoutingService

        caller_id = verified_caller_id or TelnyxNumberRoutingService.resolve_voice_from(
            destination_e164=to_e164,
            config=config,
        )
        if not caller_id:
            raise ValueError("Telnyx fallback caller ID/default outbound number is not configured")
        result = TelnyxVoiceAdapter.start_outbound_call(
            to_number=to_e164,
            from_number=caller_id,
            config=config,
            client_state={"org_id": org_id, "user_id": user_id, "appointment_id": appointment_id, "patient_id": patient_id},
        )
        now = datetime.utcnow()
        log = CallLog(
            org_id=org_id,
            user_id=user_id,
            appointment_id=appointment_id,
            patient_id=patient_id,
            provider="telnyx",
            external_call_id=result.external_id,
            direction="outbound",
            status=result.status if result.ok else "failed",
            to_number=to_e164,
            from_number=caller_id,
            llm_prompt=llm_prompt or agent.system_prompt,
            media_stream_id=agent.id,
            started_at=now if result.ok else None,
            last_status_at=now,
            raw_payload=json.dumps(
                {
                    "ok": result.ok,
                    "status": result.status,
                    "detail": result.detail,
                    "caller_id_source": "verified_user" if verified_caller_id else "fallback",
                    "agent_id": agent.id,
                    "agent_slug": agent.slug,
                    "payload": result.payload,
                },
                ensure_ascii=False,
            ),
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def log_call_event(db: Session, *, payload: dict[str, Any], org_id: str | None = None) -> CallLog | None:
        try:
            from app.services.appointment_call_service import handle_appointment_telnyx_event

            if handle_appointment_telnyx_event(db, payload):
                return None
        except Exception:
            import logging

            logging.getLogger(__name__).exception("appointment_call_telnyx_event_failed")

        try:
            from app.services.interview_call_dispatch_service import handle_interview_telnyx_event

            if handle_interview_telnyx_event(db, payload):
                return None
        except Exception:
            import logging

            logging.getLogger(__name__).exception("interview_call_telnyx_event_failed")

        try:
            from app.services.survey_call_dispatch_service import handle_survey_telnyx_event

            handle_survey_telnyx_event(db, payload)
        except Exception:
            import logging

            logging.getLogger(__name__).exception("survey_call_telnyx_event_failed")

        try:
            from app.services.lead_sales_service import handle_lead_sales_telnyx_event

            handle_lead_sales_telnyx_event(db, payload)
        except Exception:
            import logging

            logging.getLogger(__name__).exception("lead_sales_telnyx_event_failed")

        data = payload.get("data") or payload
        event_type = str(data.get("event_type") or payload.get("event_type") or "").lower()
        record = data.get("payload") if isinstance(data.get("payload"), dict) else data
        call_id = record.get("call_control_id") or record.get("call_leg_id") or record.get("id")
        if not call_id:
            return None
        log = db.execute(select(CallLog).where(CallLog.external_call_id == str(call_id))).scalar_one_or_none()
        if log is None:
            if not org_id:
                client_state = record.get("client_state")
                if isinstance(client_state, str):
                    parsed = _decode_client_state(client_state)
                    org_id = (parsed or {}).get("org_id") if parsed else None
            if not org_id:
                return None
            log = CallLog(org_id=org_id, provider="telnyx", external_call_id=str(call_id), direction="outbound")
        status = record.get("call_status") or record.get("state") or event_type.rsplit(".", 1)[-1] or log.status
        now = datetime.utcnow()
        terminal = (
            "hangup" in event_type
            or "ended" in event_type
            or str(status).lower() in {"completed", "hangup", "ended", "busy", "no-answer", "failed", "canceled", "cancelled"}
        )
        log.status = str(status)
        log.to_number = record.get("to") or record.get("to_number") or log.to_number
        log.from_number = record.get("from") or record.get("from_number") or log.from_number
        log.last_status_at = now
        if "answered" in event_type or status in {"answered", "active"}:
            log.answered_at = log.answered_at or now
        if "hangup" in event_type or "ended" in event_type or status in {"completed", "hangup", "ended"}:
            log.ended_at = log.ended_at or now
        log.raw_payload = json.dumps(payload, ensure_ascii=False)
        db.add(log)
        try:
            from app.services.telephony_recovery_bridge import apply_call_status_to_recovery

            apply_call_status_to_recovery(
                db,
                provider="telnyx",
                provider_ref=str(call_id),
                call_status=str(status),
            )
        except Exception:
            pass
        db.commit()
        db.refresh(log)
        if terminal and log.org_id and not log.usage_metered:
            try:
                from app.services.usage_wallet_service import UsageWalletService

                UsageWalletService.on_call_completed(db, org_id=log.org_id, call_log_id=log.id)
            except Exception:
                pass
        return log

    @staticmethod
    def append_transcript(db: Session, *, call_control_id: str, speaker: str, text: str, response_text: str | None = None) -> CallLog | None:
        log = db.execute(select(CallLog).where(CallLog.external_call_id == call_control_id)).scalar_one_or_none()
        if log is None:
            return None
        line = f"{speaker}: {text}".strip()
        log.transcript_text = "\n".join([x for x in [log.transcript_text, line] if x])
        if response_text:
            log.llm_response = response_text
            log.transcript_text = "\n".join([x for x in [log.transcript_text, f"agent: {response_text}"] if x])
        log.last_status_at = datetime.utcnow()
        db.add(log)
        db.commit()
        db.refresh(log)
        return log
