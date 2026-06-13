"""WhatsApp inbound handler for Abuu (shared Telnyx WA number)."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.models.entities import CustomerOrder, Restaurant
from app.abuu.services.intent_service import detect_intent, is_abuu_start_message
from app.abuu.services.location_service import (
    get_default_address,
    parse_whatsapp_location,
    save_customer_address,
    validate_delivery_radius,
)
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.reply_service import (
    address_saved_message,
    cancel_message,
    confirm_pending_payment_message,
    item_added_message,
    menu_message,
    need_delivery_address_message,
    out_of_delivery_area_message,
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

            customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone)
            lang = customer.preferred_language or "ar"
            in_abuu_flow = has_session or bool(session) or is_abuu_start_message(text)

            if in_abuu_flow and AbuuInboundService._is_voice_inbound(record):
                AbuuInboundService._send_reply(
                    main_db,
                    phone,
                    voice_fallback_message(lang, active_order=bool(session and session.active_order_id)),
                    org_id=org_id,
                )
                if session:
                    session.last_message_id = message_id
                    abuu_db.add(session)
                abuu_db.commit()
                return {"handled": True, "reason": "voice_fallback"}

            location = parse_whatsapp_location(record)
            if session and location is not None:
                result = AbuuInboundService._handle_delivery_location(
                    abuu_db,
                    main_db,
                    session=session,
                    customer=customer,
                    location=location,
                    lang=lang,
                    message_id=message_id,
                    org_id=org_id,
                )
                abuu_db.commit()
                return result

            intent = detect_intent(text, has_active_session=has_session or bool(session))

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

            context = AbuuInboundService._load_context(session)
            order = abuu_db.get(CustomerOrder, session.active_order_id) if session.active_order_id else None
            restaurant_id = str(context.get("restaurant_id") or (order.restaurant_id if order else ""))

            if session.step == "awaiting_delivery" and text and intent.name not in {"cancel", "confirm", "menu"}:
                if order is None:
                    AbuuInboundService._send_reply(main_db, phone, unknown_message(lang), org_id=org_id)
                    abuu_db.commit()
                    return {"handled": True, "action": "no_order"}
                address = save_customer_address(
                    abuu_db,
                    customer_id=customer.id,
                    address_text=text,
                    latitude=None,
                    longitude=None,
                )
                order.delivery_address_id = address.id
                abuu_db.add(order)
                session.step = "browsing"
                AbuuOrderDraftService.upsert_session(
                    abuu_db,
                    phone=phone,
                    step="browsing",
                    context=context,
                    active_order_id=order.id,
                    message_id=message_id,
                )
                AbuuInboundService._send_reply(main_db, phone, address_saved_message(lang), org_id=org_id)
                abuu_db.commit()
                return {"handled": True, "action": "address_saved"}

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
                    step=session.step,
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
                if not order.delivery_address_id:
                    default_address = get_default_address(abuu_db, customer.id)
                    if default_address is not None:
                        order.delivery_address_id = default_address.id
                        abuu_db.add(order)
                    else:
                        session.step = "awaiting_delivery"
                        AbuuOrderDraftService.upsert_session(
                            abuu_db,
                            phone=phone,
                            step="awaiting_delivery",
                            context=context,
                            active_order_id=order.id,
                            message_id=message_id,
                        )
                        AbuuInboundService._send_reply(
                            main_db,
                            phone,
                            need_delivery_address_message(lang),
                            org_id=org_id,
                        )
                        abuu_db.commit()
                        return {"handled": True, "action": "need_delivery_address"}
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
                    step=session.step,
                    context=context,
                    active_order_id=order.id,
                    message_id=message_id,
                )
                AbuuInboundService._send_reply(main_db, phone, item_added_message(item, order, lang), org_id=org_id)
                abuu_db.commit()
                return {"handled": True, "action": "item_added", "order_id": order.id}

            AbuuInboundService._send_reply(main_db, phone, unknown_message(lang), org_id=org_id)
            session.last_message_id = message_id
            abuu_db.add(session)
            abuu_db.commit()
            return {"handled": True, "action": "unknown"}

    @staticmethod
    def _load_context(session) -> dict:
        try:
            context = json.loads(session.context_json or "{}")
            return context if isinstance(context, dict) else {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _handle_delivery_location(
        abuu_db: Session,
        main_db: Session,
        *,
        session,
        customer,
        location,
        lang: str,
        message_id: str | None,
        org_id: str | None,
    ) -> dict[str, Any]:
        order = abuu_db.get(CustomerOrder, session.active_order_id) if session.active_order_id else None
        if order is None:
            AbuuInboundService._send_reply(main_db, customer.phone, unknown_message(lang), org_id=org_id)
            return {"handled": True, "action": "no_order"}

        restaurant = abuu_db.get(Restaurant, order.restaurant_id)
        if restaurant and location.latitude is not None and location.longitude is not None:
            ok, distance = validate_delivery_radius(
                restaurant,
                lat=location.latitude,
                lng=location.longitude,
            )
            if not ok:
                AbuuInboundService._send_reply(
                    main_db,
                    customer.phone,
                    out_of_delivery_area_message(
                        lang,
                        distance_km=distance,
                        radius_km=float(restaurant.delivery_radius_km or 0),
                    ),
                    org_id=org_id,
                )
                return {"handled": True, "action": "out_of_delivery_area"}

        address = save_customer_address(
            abuu_db,
            customer_id=customer.id,
            address_text=location.address_text,
            latitude=location.latitude,
            longitude=location.longitude,
        )
        order.delivery_address_id = address.id
        abuu_db.add(order)
        context = AbuuInboundService._load_context(session)
        AbuuOrderDraftService.upsert_session(
            abuu_db,
            phone=customer.phone,
            step="browsing",
            context=context,
            active_order_id=order.id,
            message_id=message_id,
        )
        AbuuInboundService._send_reply(main_db, customer.phone, address_saved_message(lang), org_id=org_id)
        return {"handled": True, "action": "address_saved", "order_id": order.id}

    @staticmethod
    def _is_voice_inbound(record: dict[str, Any] | None) -> bool:
        if not record:
            return False
        try:
            from app.services.survey_wa_inbound_parse_service import parse_telnyx_wa_inbound_record
            from app.services.survey_wa_open_text_service import is_voice_message_type
            from app.services.survey_wa_voice_note_media_service import extract_media_items

            normalized = parse_telnyx_wa_inbound_record(record, sender_phone="")
            if normalized.is_voice_note:
                return True

            for candidate in (
                record.get("type"),
                (record.get("whatsapp_message") or {}).get("type")
                if isinstance(record.get("whatsapp_message"), dict)
                else None,
            ):
                if candidate and is_voice_message_type(str(candidate)):
                    return True

            for item in extract_media_items(record):
                content_type = str(item.get("content_type") or "").lower()
                if "audio" in content_type or "ogg" in content_type:
                    return True
        except Exception:
            logger.exception("abuu_voice_detect_failed")
        return False

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
