"""Telnyx webhook tools for live interview calls (hangup + session signals)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.telnyx_voice_service import TelnyxVoiceAdapter, _decode_client_state, _telnyx_config

logger = logging.getLogger(__name__)


def _parse_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    arguments: dict[str, Any] = {}
    dynamic: dict[str, Any] = {}
    call_id = ""

    if isinstance(payload.get("arguments"), dict):
        arguments.update(payload["arguments"])
    if isinstance(payload.get("dynamic_variables"), dict):
        dynamic.update(payload["dynamic_variables"])

    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    record = data.get("payload") if isinstance(data.get("payload"), dict) else data
    if isinstance(record, dict):
        if isinstance(record.get("arguments"), dict):
            arguments = {**arguments, **record["arguments"]}
        if isinstance(record.get("dynamic_variables"), dict):
            dynamic = {**dynamic, **record["dynamic_variables"]}
        call_id = str(
            record.get("call_control_id") or record.get("call_leg_id") or record.get("id") or ""
        ).strip()
        state_raw = record.get("client_state")
        if isinstance(state_raw, str) and state_raw.strip():
            parsed = _decode_client_state(state_raw)
            if isinstance(parsed, dict):
                dynamic = {**dynamic, **{k: v for k, v in parsed.items() if v is not None}}

    call_id = call_id or str(payload.get("call_control_id") or arguments.get("call_control_id") or "").strip()
    return arguments, dynamic, call_id


def _result(recipient: ServiceOrderRecipient) -> dict[str, Any]:
    try:
        data = json.loads(recipient.result_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_result(db: Session, recipient: ServiceOrderRecipient, patch: dict[str, Any]) -> None:
    merged = _result(recipient)
    signals = merged.get("session_signals") if isinstance(merged.get("session_signals"), dict) else {}
    if isinstance(patch.get("session_signals"), dict):
        signals = {**signals, **patch.pop("session_signals")}
        merged["session_signals"] = signals
    merged.update(patch)
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    recipient.updated_at = datetime.utcnow()
    db.add(recipient)
    db.commit()
    db.refresh(recipient)


def resolve_live_interview_recipient(
    db: Session,
    *,
    call_control_id: str,
    dynamic: dict[str, Any] | None = None,
) -> tuple[ServiceOrder | None, ServiceOrderRecipient | None]:
    dynamic = dynamic or {}
    order_id = str(dynamic.get("service_order_id") or dynamic.get("order_id") or "").strip()
    recipient_id = str(dynamic.get("recipient_id") or "").strip()
    if order_id and recipient_id:
        order = db.get(ServiceOrder, order_id)
        recipient = db.get(ServiceOrderRecipient, recipient_id)
        if order is not None and recipient is not None and recipient.order_id == order.id:
            return order, recipient

    call_id = str(call_control_id or "").strip()
    if not call_id:
        return None, None

    # Live legs usually store call_control_id on the recipient result.
    rows = list(
        db.execute(
            select(ServiceOrderRecipient)
            .where(ServiceOrderRecipient.status.in_(("calling", "ringing", "in_progress", "pending")))
            .order_by(ServiceOrderRecipient.updated_at.desc())
            .limit(200)
        ).scalars()
    )
    for recipient in rows:
        merged = _result(recipient)
        if str(merged.get("call_control_id") or "").strip() == call_id:
            order = db.get(ServiceOrder, recipient.order_id)
            return order, recipient
    return None, None


def hangup_interview_call(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Force Telnyx hangup after agent goodbye (Hangup tool / end_call webhook)."""
    _arguments, dynamic, call_id = _parse_payload(payload)
    if not call_id:
        return {"ok": False, "error": "missing_call_control_id"}

    order, recipient = resolve_live_interview_recipient(db, call_control_id=call_id, dynamic=dynamic)
    telnyx_config = _telnyx_config(db)
    result = TelnyxVoiceAdapter.hangup_call(call_control_id=call_id, config=telnyx_config)
    if recipient is not None:
        _save_result(
            db,
            recipient,
            {
                "forced_hangup_at": datetime.utcnow().isoformat(),
                "forced_hangup_ok": bool(result.ok),
                "forced_hangup_status": result.status,
                "session_signals": {"hangup_tool_called": True},
            },
        )
    if not result.ok:
        logger.warning(
            "interview_forced_hangup_failed call_id=%s status=%s detail=%s",
            call_id,
            result.status,
            result.detail,
        )
        return {"ok": False, "error": result.detail or result.status, "call_control_id": call_id}
    return {
        "ok": True,
        "status": "hangup_sent",
        "call_control_id": call_id,
        "order_id": order.id if order else None,
        "recipient_id": recipient.id if recipient else None,
    }


def mark_interview_session_signal(db: Session, payload: dict[str, Any], *, signal: str) -> dict[str, Any]:
    """Store structured progress/consent signals from the live assistant."""
    arguments, dynamic, call_id = _parse_payload(payload)
    order, recipient = resolve_live_interview_recipient(db, call_control_id=call_id, dynamic=dynamic)
    if recipient is None:
        return {"ok": False, "error": "recipient_not_found"}

    signals: dict[str, Any] = {}
    sig = str(signal or "").strip().lower()
    if sig in {"recording_consent", "recording_consent_yes"}:
        signals["recording_consent"] = True
    elif sig in {"recording_declined", "recording_consent_no"}:
        signals["recording_consent"] = False
    elif sig in {"question_asked", "mark_question_asked"}:
        try:
            n = int(arguments.get("question_number") or arguments.get("n") or 0)
        except (TypeError, ValueError):
            n = 0
        existing = _result(recipient).get("session_signals") or {}
        prev = int(existing.get("questions_asked") or 0) if isinstance(existing, dict) else 0
        signals["questions_asked"] = max(prev + 1, n, 1)
        if n > 0:
            signals["last_question_number"] = n
    else:
        return {"ok": False, "error": f"unknown_signal:{sig}"}

    _save_result(
        db,
        recipient,
        {
            "session_signals": signals,
            "session_signal_updated_at": datetime.utcnow().isoformat(),
        },
    )
    return {
        "ok": True,
        "signal": sig,
        "session_signals": (_result(recipient).get("session_signals") or {}),
        "order_id": order.id if order else None,
        "recipient_id": recipient.id,
    }


def interview_tool_webhook_urls() -> dict[str, str]:
    return {
        "end_call": "https://api.voxbulk.com/interview/telnyx-tools/end_call",
        "mark_recording_consent": "https://api.voxbulk.com/interview/telnyx-tools/mark_recording_consent",
        "mark_question_asked": "https://api.voxbulk.com/interview/telnyx-tools/mark_question_asked",
    }
