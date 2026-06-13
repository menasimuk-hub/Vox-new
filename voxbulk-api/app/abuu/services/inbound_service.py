"""WhatsApp inbound handler for Abuu (shared Telnyx WA number)."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.models.entities import CustomerOrder, Restaurant
from app.abuu.services.intent_service import detect_intent, is_abuu_start_message
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.reply_service import (
    cancel_message,
    confirm_pending_payment_message,
    item_added_message,
    menu_message,
    unknown_message,
    voice_fallback_message,
    welcome_message,
)
from app.core.abuu_database import get_abuu_sessionmaker
from app.core.config import get_settings
from app.services.customer_feedback.location_service import FeedbackLocationService
from app.services.messaging_log_service import normalize_e164
from app.services.telnyx_messaging_service import TelnyxMessagingService

logger = logging.getLogger(__name__)


class AbuuInboundService:
    @staticmethod
    def try_handle(
        main_db: Session,
        *,
        from_phone: str,
        body: str,
        message_id: str | None = None,
        record: dict[str, Any] | None = None,
        org_id: str | None = None,
    ) -> dict[str, Any]:
        settings = get_settings()
        if not settings.abuu_enabled:
            return {"handled": False, "reason": "disabled"}

        text = str(body or "").strip()
        if FeedbackLocationService.parse_trigger_ref(text):
            return {"handled": False, "reason": "feedback_trigger"}

        try:
            phone = normalize_e164(from_phone)
        except ValueError:
            phone = str(from_phone or "").strip()
        if not phone:
            return {"handled": False, "reason": "missing_phone"}

        with get_abuu_sessionmaker()() as abuu_db:
            session = AbuuOrderDraftService.get_session(abuu_db, phone)
            has_session = bool(session and session.step not in {"", "idle"})
            if session and message_id and session.last_message_id == message_id:
                return {"handled": True, "duplicate": True}

            if not has_session and not is_abuu_start_message(text):
                return {"handled": False, "reason": "not_abuu"}

            if record:
                try:
                    from app.services.survey_wa_inbound_parse_service import parse_telnyx_wa_inbound_record

                    normalized = parse_telnyx_wa_inbound_record(record, sender_phone=phone)
                    if normalized.is_voice_note and not text:
                        lang = "ar"
                        AbuuInboundService._send_reply(main_db, phone, voice_fallback_message(lang), org_id=org_id)
                        return {"handled": True, "reason": "voice_fallback"}
                except Exception:
                    logger.exception("abuu_voice_parse_failed phone=%s", phone)

            intent = detect_intent(text, has_active_session=has_session or bool(session))
            customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone)
            lang = customer.preferred_language or "ar"

            if intent.name == "order_food":
                restaurant = AbuuOrderDraftService.default_restaurant(abuu_db)
                if restaurant is None:
                    AbuuInboundService._send_reply(
                        main_db,
                        phone,
                        "لا توجد مطاعم متاحة حالياً." if lang == "ar" else "No restaurants are available right now.",
                        org_id=org_id,
                    )
                    abuu_db.commit()
                    return {"handled": True, "reason": "no_restaurant"}

                order = AbuuOrderDraftService.start_draft(abuu_db, customer=customer, restaurant=restaurant)
                items = AbuuOrderDraftService.list_menu_items(abuu_db, restaurant.id)
                context = {
                    "restaurant_id": restaurant.id,
                    "suggested_items": AbuuOrderDraftService.build_suggestion_index(items),
                }
                AbuuOrderDraftService.upsert_session(
                    abuu_db,
                    phone=phone,
                    step="browsing",
                    context=context,
                    active_order_id=order.id,
                    message_id=message_id,
                )
                replies = [welcome_message(restaurant, lang)]
                if items:
                    indexed = list(enumerate(items, start=1))
                    replies.append(menu_message(restaurant, indexed, lang))
                AbuuInboundService._send_reply(main_db, phone, "\n\n".join(replies), org_id=org_id)
                abuu_db.commit()
                return {"handled": True, "action": "started", "order_id": order.id}

            if session is None:
                return {"handled": False, "reason": "no_session"}

            context = {}
            try:
                context = json.loads(session.context_json or "{}")
                if not isinstance(context, dict):
                    context = {}
            except json.JSONDecodeError:
                context = {}

            order = abuu_db.get(CustomerOrder, session.active_order_id) if session.active_order_id else None
            restaurant_id = str(context.get("restaurant_id") or (order.restaurant_id if order else ""))

            if intent.name == "cancel":
                AbuuOrderDraftService.cancel_draft(abuu_db, order)
                AbuuOrderDraftService.clear_session(abuu_db, phone)
                AbuuInboundService._send_reply(main_db, phone, cancel_message(lang), org_id=org_id)
                abuu_db.commit()
                return {"handled": True, "action": "cancelled"}

            if intent.name == "menu" and restaurant_id:
                restaurant = abuu_db.get(Restaurant, restaurant_id)
                items = AbuuOrderDraftService.list_menu_items(abuu_db, restaurant_id)
                indexed = list(enumerate(items, start=1))
                context["suggested_items"] = AbuuOrderDraftService.build_suggestion_index(items)
                AbuuOrderDraftService.upsert_session(
                    abuu_db,
                    phone=phone,
                    step="browsing",
                    context=context,
                    active_order_id=session.active_order_id,
                    message_id=message_id,
                )
                if restaurant:
                    AbuuInboundService._send_reply(main_db, phone, menu_message(restaurant, indexed, lang), org_id=org_id)
                abuu_db.commit()
                return {"handled": True, "action": "menu"}

            if intent.name == "confirm":
                if order is None:
                    AbuuInboundService._send_reply(main_db, phone, unknown_message(lang), org_id=org_id)
                    abuu_db.commit()
                    return {"handled": True, "action": "no_order"}
                try:
                    AbuuOrderDraftService.confirm_draft(abuu_db, order)
                except ValueError as exc:
                    AbuuInboundService._send_reply(main_db, phone, str(exc), org_id=org_id)
                    abuu_db.commit()
                    return {"handled": True, "action": "confirm_failed", "detail": str(exc)}
                AbuuOrderDraftService.clear_session(abuu_db, phone)
                AbuuInboundService._send_reply(main_db, phone, confirm_pending_payment_message(order, lang), org_id=org_id)
                abuu_db.commit()
                return {"handled": True, "action": "confirmed", "order_id": order.id}

            if intent.name == "add_item" and order and restaurant_id and intent.item_ref:
                item = AbuuOrderDraftService.resolve_item_from_ref(
                    abuu_db,
                    restaurant_id=restaurant_id,
                    item_ref=intent.item_ref,
                    context=context,
                )
                if item is None:
                    AbuuInboundService._send_reply(main_db, phone, unknown_message(lang), org_id=org_id)
                    session.last_message_id = message_id
                    abuu_db.add(session)
                    abuu_db.commit()
                    return {"handled": True, "action": "item_not_found"}
                order = AbuuOrderDraftService.add_item(abuu_db, order, item)
                AbuuOrderDraftService.upsert_session(
                    abuu_db,
                    phone=phone,
                    step="browsing",
                    context=context,
                    active_order_id=order.id,
                    message_id=message_id,
                )
                AbuuInboundService._send_reply(main_db, phone, item_added_message(item, order, lang), org_id=org_id)
                abuu_db.commit()
                return {"handled": True, "action": "item_added", "order_id": order.id}

            AbuuInboundService._send_reply(main_db, phone, unknown_message(lang), org_id=org_id)
            if session:
                session.last_message_id = message_id
                abuu_db.add(session)
            abuu_db.commit()
            return {"handled": True, "action": "unknown"}

    @staticmethod
    def _send_reply(main_db: Session, to_phone: str, body: str, *, org_id: str | None) -> None:
        result = TelnyxMessagingService.send_whatsapp(
            main_db,
            to_number=to_phone,
            body=body,
            org_id=org_id,
            meter_usage=False,
        )
        if not result.ok:
            logger.warning("abuu_wa_reply_failed to=%s status=%s detail=%s", to_phone, result.status, result.detail)
