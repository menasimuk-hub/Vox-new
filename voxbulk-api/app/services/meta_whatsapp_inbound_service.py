from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.whatsapp_log import WhatsAppLog
from app.services.messaging_log_service import LogService, normalize_e164
from app.services.meta_whatsapp_config_service import validate_meta_whatsapp_config
from app.services.provider_settings import ProviderSettingsService
from app.services.survey_wa_inbound_parse_service import (
    NormalizedWaInboundReply,
    log_raw_wa_inbound,
    parse_meta_wa_inbound_message,
)

logger = logging.getLogger(__name__)


def _extract_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return out
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            messages = value.get("messages")
            if isinstance(messages, list):
                metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
                for msg in messages:
                    if isinstance(msg, dict):
                        out.append({"message": msg, "metadata": metadata, "waba_id": entry.get("id")})
    return out


def _extract_statuses(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Outbound delivery receipts (sent, delivered, read, failed) from Meta webhooks."""
    out: list[dict[str, Any]] = []
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return out
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            statuses = value.get("statuses")
            if isinstance(statuses, list):
                for item in statuses:
                    if isinstance(item, dict):
                        out.append(item)
    return out


def _format_meta_status_errors(status_item: dict[str, Any]) -> str | None:
    errors = status_item.get("errors")
    if not isinstance(errors, list) or not errors:
        return None
    parts: list[str] = []
    for err in errors:
        if not isinstance(err, dict):
            continue
        title = str(err.get("title") or err.get("message") or err.get("code") or "").strip()
        if title:
            parts.append(title)
    return "; ".join(parts) if parts else None


def _apply_delivery_status(db: Session, status_item: dict[str, Any]) -> bool:
    message_id = str(status_item.get("id") or "").strip()
    raw_status = str(status_item.get("status") or "").strip().lower()
    if not message_id or not raw_status:
        return False
    mapped = "delivery_failed" if raw_status == "failed" else raw_status
    err_text = _format_meta_status_errors(status_item)
    rows = list(
        db.scalars(
            select(WhatsAppLog).where(WhatsAppLog.external_message_id == message_id)
        ).all()
    )
    if not rows:
        logger.info(
            "meta_whatsapp_status_no_log message_id=%s status=%s",
            message_id,
            raw_status,
        )
        return False
    changed = False
    for existing in rows:
        if mapped and mapped != str(existing.status or "").lower():
            existing.status = mapped
            changed = True
        if err_text:
            note = f"Delivery error: {err_text}"
            body = str(existing.body or "")
            if note not in body:
                existing.body = f"{body}\n{note}".strip() if body else note
                changed = True
        db.add(existing)
    if changed:
        db.commit()
        logger.info(
            "meta_whatsapp_status_updated message_id=%s status=%s rows=%s",
            message_id,
            mapped,
            len(rows),
        )
    return changed


def _resolve_org_id(db: Session, *, config: dict[str, Any], from_phone: str) -> str:
    for candidate in (
        str(config.get("default_messaging_org_id") or "").strip(),
        str(config.get("messaging_org_id") or "").strip(),
    ):
        if not candidate:
            continue
        row = db.execute(select(Organisation.id).where(Organisation.id == candidate)).scalar_one_or_none()
        if row:
            return candidate

    if from_phone:
        try:
            from app.services.survey_whatsapp_conversation_service import find_active_recipient_for_inbound

            order, _recipient, _via = find_active_recipient_for_inbound(db, from_phone=from_phone, org_id=None)
            if order and str(order.org_id or "").strip():
                return str(order.org_id)
        except Exception:
            pass

    fallback = db.execute(select(Organisation.id).order_by(Organisation.created_at.asc()).limit(1)).scalar_one_or_none()
    if fallback:
        return str(fallback)
    return ""


def _looks_like_uuid(value: str) -> bool:
    import re

    return bool(re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", str(value or "").strip(), re.I))


def _route_inbound_handlers(
    db: Session,
    *,
    org_id: str,
    from_phone: str,
    inbound_text: str,
    normalized: NormalizedWaInboundReply,
    message_id: str | None,
    log_id: int,
    record: dict[str, Any],
) -> dict[str, Any]:
    from app.services.telnyx_inbound_messaging_service import extract_wa_button_reply

    button_reply = extract_wa_button_reply(record)
    button_id = normalized.button_id or button_reply.get("id") or (inbound_text if _looks_like_uuid(inbound_text) else "")

    result: dict[str, Any] = {"handled_survey": False, "handled_feedback": False, "handled_interview": False}

    handled_feedback = False
    feedback_result: dict[str, Any] | None = None
    from app.services.customer_feedback.location_service import FeedbackLocationService

    feedback_trigger_token = FeedbackLocationService.parse_trigger_ref(inbound_text)
    if feedback_trigger_token:
        try:
            from app.services.customer_feedback.whatsapp_service import FeedbackWhatsappService

            feedback_result = FeedbackWhatsappService.try_handle_inbound(
                db,
                from_phone=from_phone,
                body=inbound_text,
                org_id=org_id,
                record=record if isinstance(record, dict) else None,
            )
            handled_feedback = bool(feedback_result.get("handled"))
            result["handled_feedback"] = handled_feedback
        except Exception:
            logger.exception(
                "meta_feedback_wa_inbound_handler_failed body_len=%s from_hash=%s",
                len(inbound_text or ""),
                hashlib.sha256((from_phone or "").encode()).hexdigest()[:12] if from_phone else "",
            )

    handled_survey = False
    survey_session_bug = False
    if not handled_feedback:
        try:
            from app.services.survey_whatsapp_conversation_service import try_handle_survey_whatsapp_inbound

            survey_result = try_handle_survey_whatsapp_inbound(
                db,
                from_phone=from_phone,
                body=inbound_text,
                org_id=org_id,
                log_id=log_id,
                inbound_message_id=message_id,
                inbound_reply=normalized,
            )
            if survey_result is not None:
                handled_survey = bool(survey_result.get("handled"))
                if survey_result.get("reason") == "welcome_sent_but_no_active_session":
                    survey_session_bug = True
            result["handled_survey"] = handled_survey
            result["survey_result"] = survey_result
        except Exception:
            logger.exception("meta_survey_wa_inbound_handler_failed log_id=%s from=%r", log_id, from_phone)

    if not handled_feedback and not handled_survey:
        try:
            from app.services.customer_feedback.whatsapp_service import FeedbackWhatsappService

            feedback_result = FeedbackWhatsappService.try_handle_inbound(
                db,
                from_phone=from_phone,
                body=inbound_text,
                org_id=org_id,
                record=record if isinstance(record, dict) else None,
            )
            handled_feedback = bool(feedback_result.get("handled"))
            result["handled_feedback"] = handled_feedback
        except Exception:
            logger.exception("meta_feedback_wa_session_handler_failed from=%r", from_phone)

    if not handled_feedback and not handled_survey:
        try:
            from app.services.appointment_wa_inbound_service import try_handle_inbound as try_handle_appointment_inbound

            result["handled_appointment"] = try_handle_appointment_inbound(db, from_phone, inbound_text, org_id)
        except Exception:
            logger.exception("meta_appointment_wa_inbound_handler_failed from=%r", from_phone)

    if not handled_survey and not survey_session_bug:
        try:
            from app.services.interview_whatsapp_inbound_service import (
                find_active_booking_context,
                handle_inbound_reply as handle_interview_booking_reply,
                resolve_interview_booking_intent,
            )

            booking_ctx = find_active_booking_context(db, from_phone=from_phone, org_id=org_id)
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
                    from_phone=from_phone,
                    body=inbound_text,
                    button_id=button_id,
                    button_title=button_reply.get("title") or "",
                    org_id=org_id,
                    log_id=log_id,
                )
                result["handled_interview"] = bool(interview_result.get("handled"))
        except Exception:
            logger.exception("meta_interview_wa_inbound_handler_failed from=%r", from_phone)

    if not result.get("handled_interview") and not handled_survey and not survey_session_bug and not handled_feedback:
        try:
            from app.services.sales_automation_service import SalesAutomationService

            SalesAutomationService.handle_inbound_whatsapp(
                db,
                from_phone=from_phone,
                body=inbound_text,
                log_id=log_id,
            )
        except Exception:
            pass

    return result


class MetaWhatsappInboundService:
    @staticmethod
    def handle_webhook(db: Session, *, payload: dict[str, Any]) -> dict[str, Any]:
        cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="meta_whatsapp")
        config = validate_meta_whatsapp_config(cfg or {})

        statuses = _extract_statuses(payload)
        messages = _extract_messages(payload)
        if statuses or messages:
            logger.info(
                "meta_whatsapp_webhook statuses=%s messages=%s object=%s",
                len(statuses),
                len(messages),
                payload.get("object"),
            )

        status_updated = 0
        for status_item in statuses:
            if _apply_delivery_status(db, status_item):
                status_updated += 1

        logged = 0
        routed = 0
        for item in messages:
            msg = item.get("message") if isinstance(item.get("message"), dict) else {}
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            from_phone_raw = str(msg.get("from") or "")
            try:
                from_phone = normalize_e164(from_phone_raw)
            except ValueError:
                from_phone = from_phone_raw
            if not from_phone:
                continue

            message_id = str(msg.get("id") or "").strip() or None
            org_id = _resolve_org_id(db, config=config, from_phone=from_phone)
            if not org_id:
                logger.warning("meta_whatsapp_inbound_no_org from=%s", from_phone)
                continue

            to_number = normalize_e164(str(metadata.get("display_phone_number") or config.get("whatsapp_from") or ""))

            normalized = parse_meta_wa_inbound_message(msg, sender_phone=from_phone)
            inbound_text = (normalized.normalized_answer or "").strip()
            if not inbound_text and str(msg.get("type") or "").lower() not in {"audio", "voice"}:
                inbound_text = f"[{msg.get('type') or 'message'}]"

            if message_id:
                existing = db.execute(
                    select(WhatsAppLog).where(
                        WhatsAppLog.provider == "meta_whatsapp",
                        WhatsAppLog.external_message_id == message_id,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    normalized = parse_meta_wa_inbound_message(msg, sender_phone=from_phone)
                    inbound_text = (normalized.normalized_answer or "").strip()
                    _route_inbound_handlers(
                        db,
                        org_id=org_id,
                        from_phone=from_phone,
                        inbound_text=inbound_text,
                        normalized=normalized,
                        message_id=message_id,
                        log_id=int(existing.id),
                        record=msg,
                    )
                    continue

            cross = LogService.find_cross_provider_inbound_duplicate(
                db,
                from_number=from_phone,
                body=inbound_text,
                current_provider="meta_whatsapp",
            )
            if cross is not None:
                route_result = _route_inbound_handlers(
                    db,
                    org_id=org_id,
                    from_phone=from_phone,
                    inbound_text=inbound_text,
                    normalized=normalized,
                    message_id=message_id,
                    log_id=int(cross.id),
                    record=msg,
                )
                if any(
                    route_result.get(key)
                    for key in ("handled_survey", "handled_feedback", "handled_interview", "handled_appointment")
                ):
                    routed += 1
                continue

            log_raw_wa_inbound(
                record=msg,
                org_id=org_id,
                message_id=message_id,
                sender_phone=from_phone,
            )

            from app.services.connection.resolver import ConnectionProfileResolver

            inbound_profile = ConnectionProfileResolver.resolve_whatsapp_by_business_number(db, to_number=to_number)
            connection_profile_id = str(inbound_profile.id) if inbound_profile else None

            try:
                row = LogService.create_whatsapp_log(
                    db,
                    org_id=org_id,
                    direction="inbound",
                    from_number=from_phone,
                    to_number=to_number,
                    body=inbound_text or "(no text)",
                    status="received",
                    external_message_id=message_id,
                    provider="meta_whatsapp",
                    connection_profile_id=connection_profile_id,
                    raw_payload=json.dumps(msg, ensure_ascii=False),
                )
                logged += 1
            except Exception:
                logger.exception("meta_whatsapp_inbound_log_failed from=%s", from_phone)
                continue

            route_result = _route_inbound_handlers(
                db,
                org_id=org_id,
                from_phone=from_phone,
                inbound_text=inbound_text,
                normalized=normalized,
                message_id=message_id,
                log_id=int(row.id),
                record=msg,
            )
            if any(
                route_result.get(key)
                for key in ("handled_survey", "handled_feedback", "handled_interview", "handled_appointment")
            ):
                routed += 1

        return {"ok": True, "logged": logged, "routed": routed, "status_updated": status_updated}
