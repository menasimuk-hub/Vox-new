from __future__ import annotations

import json
import logging
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.models.organisation import Organisation
from app.models.whatsapp_log import WhatsAppLog
from app.services.messaging_log_service import LogService, normalize_e164
from app.services.provider_settings import ProviderSettingsService


def _extract_delivery_status(record: dict[str, Any]) -> str:
    to_entries = record.get("to")
    if isinstance(to_entries, list) and to_entries:
        first = to_entries[0]
        if isinstance(first, dict):
            to_status = str(first.get("status") or "").strip().lower()
            if to_status:
                return to_status
    return str(record.get("status") or "").strip().lower()


def _format_delivery_errors(record: dict[str, Any]) -> str | None:
    errors = record.get("errors")
    if not isinstance(errors, list) or not errors:
        return None
    parts: list[str] = []
    for item in errors:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        detail = str(item.get("detail") or item.get("title") or "").strip()
        meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
        meta_bits = []
        for key in ("error_user_msg", "error_user_title", "reason", "message"):
            val = str(meta.get(key) or "").strip()
            if val:
                meta_bits.append(val)
        if code and detail:
            parts.append(f"{code}: {detail}")
        elif detail:
            parts.append(detail)
        elif code:
            parts.append(code)
        if meta_bits:
            parts.append(" — ".join(meta_bits))
    return " · ".join(parts) if parts else None


def _phone_from(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("phone_number") or value.get("number") or "").strip()
    return str(value or "").strip()


def _looks_like_uuid(value: str) -> bool:
    import re

    return bool(
        re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            str(value or "").strip(),
            re.I,
        )
    )


def _deep_find_button_reply(value: Any, *, depth: int = 0) -> dict[str, str] | None:
    if depth > 12:
        return None
    if isinstance(value, dict):
        nested = value.get("button_reply")
        if isinstance(nested, dict):
            reply = {
                "id": str(nested.get("id") or nested.get("payload") or "").strip(),
                "title": str(nested.get("title") or nested.get("text") or "").strip(),
            }
            if reply["id"] or reply["title"]:
                return reply
        quick = value.get("quick_reply")
        if isinstance(quick, dict):
            reply = {
                "id": str(quick.get("id") or quick.get("payload") or "").strip(),
                "title": str(quick.get("title") or quick.get("text") or "").strip(),
            }
            if reply["id"] or reply["title"]:
                return reply
        if str(value.get("type") or "").lower() in {"button_reply", "quick_reply"}:
            reply = {
                "id": str(value.get("id") or value.get("payload") or "").strip(),
                "title": str(value.get("title") or value.get("text") or "").strip(),
            }
            if reply["id"] or reply["title"]:
                return reply
        for nested_value in value.values():
            if isinstance(nested_value, (dict, list)):
                found = _deep_find_button_reply(nested_value, depth=depth + 1)
                if found:
                    return found
    elif isinstance(value, list):
        for item in value:
            found = _deep_find_button_reply(item, depth=depth + 1)
            if found:
                return found
    return None


def extract_wa_button_reply(record: dict[str, Any]) -> dict[str, str]:
    found = _deep_find_button_reply(record) or {}
    return {
        "id": str(found.get("id") or "").strip(),
        "title": str(found.get("title") or "").strip(),
    }


def _extract_message_text(record: dict[str, Any]) -> str:
    button = extract_wa_button_reply(record)
    if button.get("title"):
        return button["title"]

    text = record.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    body = record.get("body")
    if isinstance(body, str) and body.strip():
        clean = body.strip()
        if not _looks_like_uuid(clean):
            return clean
    if isinstance(body, dict):
        inner = body.get("text")
        if isinstance(inner, str) and inner.strip():
            return inner.strip()
        if isinstance(inner, dict):
            nested = inner.get("body")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        if str(body.get("type") or "").lower() == "text":
            text_obj = body.get("text")
            if isinstance(text_obj, dict):
                nested = text_obj.get("body")
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()

    whatsapp_message = record.get("whatsapp_message")
    if isinstance(whatsapp_message, dict):
        if str(whatsapp_message.get("type") or "").lower() == "text":
            text_obj = whatsapp_message.get("text")
            if isinstance(text_obj, dict):
                nested = text_obj.get("body")
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
        if str(whatsapp_message.get("type") or "").lower() in {"button", "interactive", "quick_reply"}:
            for key in ("button", "interactive", "button_reply", "list_reply", "quick_reply"):
                block = whatsapp_message.get(key)
                if isinstance(block, dict):
                    for field in ("text", "title", "description", "id"):
                        val = block.get(field)
                        if isinstance(val, str) and val.strip():
                            return val.strip()
                    nested = block.get("button_reply") or block.get("list_reply")
                    if isinstance(nested, dict):
                        for field in ("text", "title", "description", "id"):
                            val = nested.get(field)
                            if isinstance(val, str) and val.strip():
                                return val.strip()

    for key in ("button_text", "title", "payload", "reply"):
        val = record.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    return _deep_wa_reply_text(record)


def _deep_wa_reply_text(value: Any, *, depth: int = 0) -> str:
    if depth > 8:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        if "button_reply" in value and isinstance(value["button_reply"], dict):
            nested = value["button_reply"]
            for key in ("title", "text", "description"):
                val = nested.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        for key in ("title", "text", "body", "description", "payload", "reply", "id"):
            found = _deep_wa_reply_text(value.get(key), depth=depth + 1)
            if found and not (_looks_like_uuid(found) and key == "id"):
                return found
            if found and key != "id":
                return found
        for key in ("button_reply", "list_reply", "interactive", "whatsapp_message", "message", "payload"):
            found = _deep_wa_reply_text(value.get(key), depth=depth + 1)
            if found:
                return found
        for nested in value.values():
            if isinstance(nested, (dict, list)):
                found = _deep_wa_reply_text(nested, depth=depth + 1)
                if found:
                    return found
    if isinstance(value, list):
        for item in value:
            found = _deep_wa_reply_text(item, depth=depth + 1)
            if found:
                return found
    return ""


def _resolve_org_id(db: Session, *, header_org_id: str | None, config: dict[str, Any]) -> str:
    for candidate in (
        str(header_org_id or "").strip(),
        str(config.get("messaging_org_id") or "").strip(),
        str(config.get("default_messaging_org_id") or "").strip(),
    ):
        if not candidate:
            continue
        row = db.execute(select(Organisation.id).where(Organisation.id == candidate)).scalar_one_or_none()
        if row:
            return candidate
    fallback = db.execute(select(Organisation.id).order_by(Organisation.created_at.asc()).limit(1)).scalar_one_or_none()
    if fallback:
        return str(fallback)
    raise ValueError("No organisation found to attach inbound Telnyx messages — create an org or set messaging_org_id in Telnyx settings.")


def _message_channel(msg_type: str) -> str:
    clean = str(msg_type or "").strip().lower()
    return "whatsapp" if "whatsapp" in clean else "sms"


class TelnyxInboundMessagingService:
    @staticmethod
    def handle_webhook(db: Session, payload: dict[str, Any], *, header_org_id: str | None = None) -> dict[str, Any]:
        # TELNYX_WEBHOOK_BUILD_MARKER_20260606_2250 — service inbound instrumentation
        from app.core.runtime_build_info import WEBHOOK_BUILD_MARKER, log_webhook_entry

        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        event_type = str(data.get("event_type") or payload.get("event_type") or "").strip().lower()
        record = data.get("payload") if isinstance(data.get("payload"), dict) else data
        from_number_early = _phone_from(record.get("from"))
        log_webhook_entry(
            event_type=event_type,
            from_phone=from_number_early,
            org_id=header_org_id,
            handler="app.services.telnyx_inbound_messaging_service.TelnyxInboundMessagingService.handle_webhook",
        )
        logger.info(
            "%s service_handle_webhook file=app/services/telnyx_inbound_messaging_service.py",
            WEBHOOK_BUILD_MARKER,
        )

        if event_type and event_type not in {"message.received", "message.sent", "message.finalized"}:
            return {"ok": True, "ignored": True, "event_type": event_type}

        message_id = str(record.get("id") or record.get("message_id") or "").strip() or None
        direction = str(record.get("direction") or "inbound").strip().lower()
        msg_type = str(record.get("type") or record.get("record_type") or "SMS")
        channel = _message_channel(msg_type)

        from_number = _phone_from(record.get("from"))
        to_entries = record.get("to")
        to_number = ""
        if isinstance(to_entries, list) and to_entries:
            to_number = _phone_from(to_entries[0])
        elif isinstance(to_entries, dict):
            to_number = _phone_from(to_entries)

        body = _extract_message_text(record)
        status = _extract_delivery_status(record) or ("received" if direction == "inbound" else "sent")
        delivery_error = _format_delivery_errors(record)

        cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
        config = cfg if isinstance(cfg, dict) else {}
        org_id = _resolve_org_id(db, header_org_id=header_org_id, config=config)

        try:
            from_norm = normalize_e164(from_number) if from_number else from_number
        except ValueError:
            from_norm = from_number
        try:
            to_norm = normalize_e164(to_number) if to_number else to_number
        except ValueError:
            to_norm = to_number

        if message_id:
            existing = db.execute(
                select(WhatsAppLog).where(
                    WhatsAppLog.provider == "telnyx",
                    WhatsAppLog.external_message_id == message_id,
                )
            ).scalar_one_or_none()
            if existing is not None:
                if status and status != existing.status:
                    existing.status = status
                    if body and not existing.body:
                        existing.body = body
                    if delivery_error:
                        err_note = f"Delivery error: {delivery_error}"
                        if err_note not in str(existing.body or ""):
                            existing.body = f"{existing.body or ''}\n{err_note}".strip()
                    db.add(existing)
                    db.commit()
                if direction == "outbound":
                    try:
                        from app.services.telephony_recovery_bridge import apply_message_status_to_recovery

                        for provider in ("telnyx_whatsapp", "telnyx_sms"):
                            apply_message_status_to_recovery(
                                db,
                                provider=provider,
                                provider_ref=message_id,
                                message_status=status,
                            )
                        db.commit()
                    except Exception:
                        pass
                result: dict[str, Any] = {
                    "ok": True,
                    "log_id": existing.id,
                    "duplicate": True,
                    "status": status,
                }
                if direction == "inbound" and channel == "whatsapp":
                    try:
                        from app.services.survey_wa_inbound_parse_service import (
                            parse_telnyx_wa_inbound_record,
                        )
                        from app.services.survey_whatsapp_conversation_service import (
                            try_handle_survey_whatsapp_inbound,
                        )

                        normalized_dup = parse_telnyx_wa_inbound_record(
                            record,
                            sender_phone=from_norm or from_number or "",
                        )
                        inbound_dup_text = (
                            normalized_dup.normalized_answer or body or ""
                        ).strip()
                        survey_result = try_handle_survey_whatsapp_inbound(
                            db,
                            from_phone=from_norm or from_number,
                            body=inbound_dup_text,
                            org_id=org_id,
                            log_id=existing.id,
                            inbound_message_id=message_id,
                            inbound_reply=normalized_dup,
                        )
                        if survey_result is not None:
                            result["survey"] = survey_result
                            if survey_result.get("duplicate"):
                                result["survey_duplicate_skipped"] = True
                    except Exception:
                        logger.exception(
                            "survey_wa_inbound_handler_failed duplicate=True log_id=%s message_id=%s from=%r",
                            existing.id,
                            message_id,
                            from_norm or from_number,
                        )
                return result

        if direction != "inbound" and event_type != "message.received":
            if direction == "outbound" and event_type in {"message.sent", "message.finalized"} and message_id:
                pass
            else:
                return {"ok": True, "ignored": True, "event_type": event_type, "direction": direction}

        media = record.get("media")
        media_json = json.dumps(media, ensure_ascii=False)[:8000] if media else None
        raw_payload = json.dumps(payload, ensure_ascii=False)[:8000]

        row = WhatsAppLog(
            org_id=org_id,
            provider="telnyx",
            external_message_id=message_id,
            status=status or ("received" if direction == "inbound" else "sent"),
            direction="inbound" if direction == "inbound" else "outbound",
            to_number=to_norm or None,
            from_number=from_norm or None,
            body=(body or f"({channel} message)") + (f"\nDelivery error: {delivery_error}" if delivery_error else ""),
            media_json=media_json,
            raw_payload=raw_payload,
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        if direction == "inbound" and channel == "whatsapp":
            handled_interview = False
            handled_survey = False
            survey_session_bug = False
            from app.services.survey_wa_inbound_parse_service import (
                log_raw_telnyx_inbound,
                parse_telnyx_wa_inbound_record,
            )

            log_raw_telnyx_inbound(
                record=record,
                org_id=org_id,
                message_id=message_id,
                sender_phone=from_norm or from_number,
            )
            normalized = parse_telnyx_wa_inbound_record(
                record,
                sender_phone=from_norm or from_number or "",
            )
            button_reply = extract_wa_button_reply(record)
            inbound_text = (normalized.normalized_answer or _extract_message_text(record) or body or "").strip()
            button_id = normalized.button_id or button_reply.get("id") or (
                inbound_text if _looks_like_uuid(inbound_text) else ""
            )

            # Survey WA is isolated from interview booking: route survey first when applicable.
            try:
                from app.services.survey_whatsapp_conversation_service import (
                    try_handle_survey_whatsapp_inbound,
                )

                survey_result = try_handle_survey_whatsapp_inbound(
                    db,
                    from_phone=from_norm or from_number,
                    body=inbound_text,
                    org_id=org_id,
                    log_id=row.id,
                    inbound_message_id=message_id,
                    inbound_reply=normalized,
                )
                if survey_result is not None:
                    handled_survey = bool(survey_result.get("handled"))
                    if survey_result.get("reason") == "welcome_sent_but_no_active_session":
                        survey_session_bug = True
                        logger.error(
                            "welcome_sent_but_no_active_session org=%s from=%r body=%r — "
                            "blocking sales/generic fallback",
                            org_id,
                            from_norm or from_number,
                            (inbound_text or "")[:80],
                        )
                    if survey_result.get("duplicate"):
                        logger.info(
                            "survey_wa_inbound_duplicate_skipped log_id=%s message_id=%s recipient=%s",
                            row.id,
                            message_id,
                            survey_result.get("recipient_id"),
                        )
            except Exception:
                logger.exception(
                    "survey_wa_inbound_handler_failed log_id=%s message_id=%s from=%r body=%r",
                    row.id,
                    message_id,
                    from_norm or from_number,
                    (body or "")[:120],
                )

            if not handled_survey:
                try:
                    from app.services.interview_whatsapp_inbound_service import (
                        find_active_booking_context,
                        handle_inbound_reply as handle_interview_booking_reply,
                        resolve_interview_booking_intent,
                    )

                    booking_ctx = find_active_booking_context(
                        db,
                        from_phone=from_norm or from_number,
                        org_id=org_id,
                    )
                    intent = resolve_interview_booking_intent(
                        db,
                        body=inbound_text,
                        button_id=button_id,
                        button_title=button_reply.get("title") or "",
                        org_id=org_id,
                        order=booking_ctx[1] if booking_ctx else None,
                    )
                    if intent or (booking_ctx is not None and (inbound_text or button_id)):
                        interview_result = handle_interview_booking_reply(
                            db,
                            from_phone=from_norm or from_number,
                            body=inbound_text,
                            button_id=button_id,
                            button_title=button_reply.get("title") or "",
                            org_id=org_id,
                            log_id=row.id if direction == "inbound" else None,
                        )
                        handled_interview = bool(interview_result.get("handled"))
                        if not handled_interview:
                            logger.warning(
                                "interview_wa_inbound_not_handled body=%r button_id=%r button_title=%r intent=%s reason=%s",
                                inbound_text[:120],
                                button_id[:80] if button_id else "",
                                (button_reply.get("title") or "")[:80],
                                intent,
                                interview_result.get("reason"),
                            )
                except Exception:
                    logger.exception(
                        "interview_wa_inbound_handler_failed body=%r from=%r",
                        (body or "")[:120],
                        from_norm or from_number,
                    )
            if not handled_interview and not handled_survey and not survey_session_bug:
                logger.warning(
                    "inbound_fallback_after_survey_miss org=%s from=%r body=%r — "
                    "no active survey session; routing to sales/generic handlers",
                    org_id,
                    from_norm or from_number,
                    (body or "")[:80],
                )
                try:
                    from app.services.sales_automation_service import SalesAutomationService

                    SalesAutomationService.handle_inbound_whatsapp(
                        db,
                        from_phone=from_norm or from_number,
                        body=body,
                        log_id=row.id,
                    )
                except Exception:
                    pass

        if message_id and direction == "outbound":
            try:
                from app.services.telephony_recovery_bridge import apply_message_status_to_recovery

                for provider in ("telnyx_whatsapp", "telnyx_sms"):
                    apply_message_status_to_recovery(
                        db,
                        provider=provider,
                        provider_ref=message_id,
                        message_status=status,
                    )
                db.commit()
            except Exception:
                pass

        return {"ok": True, "log_id": row.id, "channel": channel, "org_id": org_id}
