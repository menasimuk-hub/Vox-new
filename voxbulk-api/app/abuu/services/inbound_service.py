"""WhatsApp inbound handler for Abuu (shared Telnyx WA number)."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.abuu.models.entities import CustomerOrder, Restaurant
from app.abuu.services.abuu_voice_service import AbuuVoiceService, is_low_quality_transcript
from app.abuu.voice_interpretation import VoiceInterpretationService
from app.abuu.services.customer_memory_service import (
    apply_saved_address_to_order,
    first_name,
    remember_preference,
    save_customer_name,
    saved_address_summary,
)
from app.abuu.services.event_idempotency_service import AbuuEventIdempotencyService, payload_hash
from app.abuu.services.inbound_message_service import AbuuInboundMessageService
from app.abuu.agent.agent import AbuuAgentLoop, _deepseek_platform_ready
from app.abuu.conversation.orchestrator import AbuuConversationOrchestrator
from app.abuu.conversation.wa_sanitize import wa_customer_sanitize
from app.abuu.services.conversation_ai_service import classify_turn
from app.abuu.services.intent_service import detect_intent, is_abuu_start_message
from app.abuu.services.skill_definitions import SKILL_CAPTURE_LOCATION, SKILL_CONFIRM_ORDER
from app.abuu.services.skill_router import AbuuSkillRouter, TurnContext
from app.abuu.services.location_service import (
    attach_default_address_if_present,
    forward_geocode,
    normalize_address_text,
    parse_whatsapp_location,
    save_customer_address,
    validate_delivery_radius,
)
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.order_service import AbuuOrderService
from app.abuu.services.order_substitution_service import AbuuOrderSubstitutionService
from app.abuu.services.preference_service import match_food_categories
from app.abuu.services.reply_service import (
    address_saved_message,
    already_confirmed_message,
    ask_name_message,
    cancel_message,
    category_clarification_message,
    confirm_pending_payment_message,
    order_sent_to_restaurant_message,
    item_added_message,
    menu_message,
    location_clarification_message,
    need_delivery_address_message,
    out_of_delivery_area_message,
    personalized_greeting_message,
    preference_menu_message,
    unknown_message,
    voice_low_confidence_message,
    voice_unclear_transcript_message,
)
from app.core.abuu_database import get_abuu_sessionmaker
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
        if FeedbackLocationService.is_feedback_intent_message(text):
            return {"handled": False, "reason": "feedback_intent"}

        try:
            phone = normalize_e164(from_phone)
        except ValueError:
            phone = str(from_phone or "").strip()
        if not phone:
            return {"handled": False, "reason": "missing_phone"}

        with get_abuu_sessionmaker()() as abuu_db:
            session = AbuuOrderDraftService.get_session(abuu_db, phone)
            has_session = bool(session and session.step not in {"", "idle"})
            if not has_session and not is_abuu_start_message(text) and not AbuuInboundService._is_voice_inbound(record):
                return {"handled": False, "reason": "not_abuu"}

            message_type = "voice" if AbuuInboundService._is_voice_inbound(record) else "text"
            idem_payload = {"body": text, "message_type": message_type}
            idem_key = (
                f"wa:{message_id}"
                if message_id
                else f"wa:{phone}:{payload_hash({'body': text, 'record': record or {}, 'message_type': message_type})}"
            )
            event = AbuuEventIdempotencyService.begin_event(
                abuu_db,
                source="whatsapp",
                event_type="inbound_message",
                idempotency_key=idem_key,
                source_message_id=message_id,
                payload=idem_payload,
            )
            if event.is_duplicate:
                abuu_db.commit()
                return {"handled": True, "duplicate": True}

            customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone)
            lang = customer.preferred_language or "ar"
            transcript_confidence: float | None = None
            voice_meta: dict[str, Any] = {}
            logger.info(
                "abuu_wa_trace IN phone=%s type=%s text=%r",
                phone,
                message_type,
                text[:200] if message_type == "text" else "[voice-note]",
            )

            if message_type == "voice":
                voice = AbuuVoiceService.transcribe_inbound(
                    main_db,
                    record=record or {},
                    customer_phone=phone,
                    language=lang,
                )
                voice_meta = {
                    "media_url": voice.media_url,
                    "content_type": voice.content_type,
                    "storage_path": voice.storage_path,
                    "error": voice.error,
                }
                transcript_confidence = voice.confidence
                if not voice.ok:
                    partial = str(voice.transcript or "").strip()
                    if partial and not is_low_quality_transcript(partial):
                        text = partial
                    else:
                        context = {}
                        if session:
                            context = AbuuInboundService._load_context(session)
                        if not context.get("voice_clarification_sent"):
                            AbuuInboundService._send_reply(
                                main_db,
                                phone,
                                voice_low_confidence_message(lang),
                                org_id=org_id,
                            )
                            context["voice_clarification_sent"] = True
                            if session:
                                AbuuOrderDraftService.upsert_session(
                                    abuu_db,
                                    phone=phone,
                                    step=session.step,
                                    context=context,
                                    active_order_id=session.active_order_id,
                                    message_id=message_id,
                                )
                        if session:
                            session.last_message_id = message_id
                            abuu_db.add(session)
                        AbuuInboundMessageService.save(
                            abuu_db,
                            customer_phone=phone,
                            customer_id=customer.id,
                            source_message_id=message_id,
                            message_type="voice",
                            body_text=text or None,
                            transcript_text=voice.transcript or None,
                            transcript_confidence=voice.confidence,
                            voice_media_url=voice.media_url,
                            voice_content_type=voice.content_type,
                            voice_storage_path=voice.storage_path,
                            payload=voice_meta,
                        )
                        abuu_db.commit()
                        return {"handled": True, "reason": "voice_low_confidence", "confidence": voice.confidence}
                if is_low_quality_transcript(voice.transcript):
                    AbuuInboundService._send_reply(
                        main_db,
                        phone,
                        voice_unclear_transcript_message(lang),
                        org_id=org_id,
                    )
                    if session:
                        session.last_message_id = message_id
                        abuu_db.add(session)
                    AbuuInboundMessageService.save(
                        abuu_db,
                        customer_phone=phone,
                        customer_id=customer.id,
                        source_message_id=message_id,
                        message_type="voice",
                        body_text=text or None,
                        transcript_text=voice.transcript or None,
                        transcript_confidence=voice.confidence,
                        voice_media_url=voice.media_url,
                        voice_content_type=voice.content_type,
                        voice_storage_path=voice.storage_path,
                        payload=voice_meta,
                    )
                    abuu_db.commit()
                    return {
                        "handled": True,
                        "reason": "voice_unclear_transcript",
                        "transcript": voice.transcript,
                    }
                text = voice.transcript
                voice_interpretation_payload: dict[str, Any] | None = None
                if text and VoiceInterpretationService.enabled():
                    from app.abuu.agent.session import load_session, save_session

                    agent_session = load_session(abuu_db, phone)
                    interpretation = VoiceInterpretationService.interpret(
                        abuu_db,
                        main_db,
                        transcript=text,
                        stt_confidence=float(voice.confidence or 0.0),
                        session=agent_session,
                        customer=customer,
                        lang=lang,
                    )
                    VoiceInterpretationService.log_internal(interpretation)
                    voice_interpretation_payload = interpretation.to_context_json()
                    voice_meta["voice_interpretation"] = voice_interpretation_payload

                    if interpretation.needs_clarification and interpretation.clarification_prompt:
                        context = AbuuInboundService._load_context(session) if session else {}
                        if not context.get("voice_clarification_sent"):
                            AbuuInboundService._send_reply(
                                main_db,
                                phone,
                                interpretation.clarification_prompt,
                                org_id=org_id,
                            )
                            context["voice_clarification_sent"] = True
                            agent_session.context["voice_interpretation"] = voice_interpretation_payload
                            save_session(abuu_db, agent_session, message_id=message_id)
                            if session:
                                AbuuOrderDraftService.upsert_session(
                                    abuu_db,
                                    phone=phone,
                                    step=session.step,
                                    context=context,
                                    active_order_id=session.active_order_id,
                                    message_id=message_id,
                                )
                            if session:
                                session.last_message_id = message_id
                                abuu_db.add(session)
                            AbuuInboundMessageService.save(
                                abuu_db,
                                customer_phone=phone,
                                customer_id=customer.id,
                                source_message_id=message_id,
                                message_type="voice",
                                body_text=text or None,
                                transcript_text=voice.transcript or None,
                                transcript_confidence=voice.confidence,
                                voice_media_url=voice.media_url,
                                voice_content_type=voice.content_type,
                                voice_storage_path=voice.storage_path,
                                payload=voice_meta,
                            )
                            abuu_db.commit()
                            return {
                                "handled": True,
                                "reason": "voice_clarification",
                                "clarification_reason": interpretation.clarification_reason,
                            }
                    text = interpretation.corrected_transcript
                    agent_session.context["voice_interpretation"] = voice_interpretation_payload
                    if not interpretation.needs_clarification:
                        agent_session.context.pop("voice_clarification_sent", None)
                    save_session(abuu_db, agent_session, message_id=message_id)
                AbuuInboundMessageService.save(
                    abuu_db,
                    customer_phone=phone,
                    customer_id=customer.id,
                    source_message_id=message_id,
                    message_type="voice",
                    body_text=text or None,
                    transcript_text=voice.transcript or None,
                    transcript_confidence=voice.confidence,
                    voice_media_url=voice.media_url,
                    voice_content_type=voice.content_type,
                    voice_storage_path=voice.storage_path,
                    payload=voice_meta,
                )
            else:
                AbuuInboundMessageService.save(
                    abuu_db,
                    customer_phone=phone,
                    customer_id=customer.id,
                    source_message_id=message_id,
                    message_type="text",
                    body_text=text or None,
                    payload={"body": text},
                )

            in_abuu_flow = has_session or bool(session) or is_abuu_start_message(text) or message_type == "voice"
            if not in_abuu_flow:
                abuu_db.commit()
                return {"handled": False, "reason": "not_abuu"}

            if message_type == "voice" and text:
                if AbuuInboundService._should_use_orchestrator(session):
                    result = AbuuInboundService._run_orchestrator_turn(
                        abuu_db,
                        main_db,
                        phone=phone,
                        text=text,
                        session=session,
                        message_id=message_id,
                        org_id=org_id,
                    )
                    abuu_db.commit()
                    return result

                use_voice_agent = AbuuInboundService._should_use_voice_agent(main_db) and not AbuuInboundService._should_use_legacy_text_flow(
                    text, session
                )
                if use_voice_agent:
                    if not get_settings().abuu_agent_waiter_mode:
                        AbuuInboundService._send_agent_ack(main_db, phone, lang, org_id=org_id)
                    result = AbuuAgentLoop.run(
                        abuu_db,
                        main_db,
                        phone=phone,
                        text=text,
                        message_id=message_id,
                        org_id=org_id,
                        input_source="voice",
                    )
                    reply = result.get("reply")
                    if reply:
                        AbuuInboundService._send_reply(main_db, phone, reply, org_id=org_id)
                    abuu_db.commit()
                    return result

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

            result = AbuuInboundService._process_text_turn(
                abuu_db,
                main_db,
                phone=phone,
                text=text,
                session=session,
                customer=customer,
                lang=lang,
                message_id=message_id,
                org_id=org_id,
                transcript_confidence=transcript_confidence,
            )
            abuu_db.commit()
            return result

    @staticmethod
    def _process_text_turn(
        abuu_db: Session,
        main_db: Session,
        *,
        phone: str,
        text: str,
        session,
        customer,
        lang: str,
        message_id: str | None,
        org_id: str | None,
        transcript_confidence: float | None = None,
    ) -> dict[str, Any]:
        order = abuu_db.get(CustomerOrder, session.active_order_id) if session and session.active_order_id else None
        if session and session.step == "awaiting_substitution" and customer and order and (text or "").strip():
            result = AbuuOrderSubstitutionService.handle_customer_reply(
                abuu_db,
                session=session,
                order=order,
                customer=customer,
                text=text.strip(),
                lang=lang,
            )
            reply = result.get("reply")
            if reply:
                AbuuInboundService._send_reply(main_db, phone, reply, org_id=org_id)
            if session:
                session.last_message_id = message_id
                abuu_db.add(session)
            if result.get("handled"):
                return result

        if AbuuInboundService._should_use_orchestrator(session):
            result = AbuuInboundService._run_orchestrator_turn(
                abuu_db,
                main_db,
                phone=phone,
                text=text,
                session=session,
                customer=customer,
                lang=lang,
                message_id=message_id,
                org_id=org_id,
            )
            if transcript_confidence is not None:
                result["transcript_confidence"] = transcript_confidence
            return result

        if AbuuInboundService._should_use_agent_text_flow(main_db, text, session):
            result = AbuuAgentLoop.run(
                abuu_db,
                main_db,
                phone=phone,
                text=text,
                message_id=message_id,
                org_id=org_id,
            )
            reply = result.get("reply")
            if reply:
                AbuuInboundService._send_reply(main_db, phone, reply, org_id=org_id)
                if session:
                    session.last_message_id = message_id
                    abuu_db.add(session)
                payload = dict(result)
                if transcript_confidence is not None:
                    payload["transcript_confidence"] = transcript_confidence
                return payload

        has_session = bool(session and session.step not in {"", "idle"})
        step = session.step if session else None
        context = AbuuInboundService._load_context(session) if session else {}
        order = abuu_db.get(CustomerOrder, session.active_order_id) if session and session.active_order_id else None
        restaurant_id = str(context.get("restaurant_id") or (order.restaurant_id if order else ""))

        classification = classify_turn(
            main_db,
            text=text,
            step=step,
            has_session=has_session or bool(session),
            lang=lang,
            session_context=context,
        )

        # Legacy menu command
        intent = detect_intent(text, has_active_session=has_session or bool(session), step=step)
        if intent.name == "menu" and restaurant_id and session:
            restaurant = abuu_db.get(Restaurant, restaurant_id)
            categories = context.get("active_categories") or []
            items = AbuuOrderDraftService.list_menu_items(
                abuu_db,
                restaurant_id,
                categories=categories or None,
                customer=customer,
            )
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
                if categories:
                    reply = preference_menu_message(restaurant, indexed, categories=categories, lang=lang)
                else:
                    reply = menu_message(restaurant, indexed, lang)
                AbuuInboundService._send_reply(main_db, phone, reply, org_id=org_id)
            return {"handled": True, "action": "menu"}

        if session and session.step == "awaiting_delivery" and text and classification.skill == SKILL_CAPTURE_LOCATION:
            return AbuuInboundService._handle_typed_address(
                abuu_db,
                main_db,
                phone=phone,
                session=session,
                order=order,
                customer=customer,
                text=text,
                context=context,
                lang=lang,
                message_id=message_id,
                org_id=org_id,
            )

        if classification.skill == SKILL_CONFIRM_ORDER and session and order:
            if order.status == "confirmed":
                AbuuInboundService._send_reply(main_db, phone, already_confirmed_message(lang), org_id=org_id)
                return {"handled": True, "action": "already_confirmed"}
            fingerprint = AbuuOrderDraftService.cart_fingerprint(abuu_db, order)
            if context.get("confirmed_cart_fingerprint") == fingerprint and order.status == "confirmed":
                AbuuInboundService._send_reply(main_db, phone, already_confirmed_message(lang), org_id=org_id)
                return {"handled": True, "action": "already_confirmed"}
            if not attach_default_address_if_present(abuu_db, order, customer):
                order.location_missing = True
                abuu_db.add(order)
                context["confirm_after_address"] = True
                context["pending_confirm_fingerprint"] = fingerprint
                AbuuOrderDraftService.upsert_session(
                    abuu_db,
                    phone=phone,
                    step="awaiting_delivery",
                    context=context,
                    active_order_id=order.id,
                    message_id=message_id,
                )
                AbuuInboundService._send_reply(main_db, phone, need_delivery_address_message(lang), org_id=org_id)
                return {"handled": True, "action": "need_delivery_address"}
            return AbuuInboundService._finalize_confirm(
                abuu_db,
                main_db,
                phone=phone,
                order=order,
                lang=lang,
                org_id=org_id,
                context=context,
            )

        turn = TurnContext(
            abuu_db=abuu_db,
            main_db=main_db,
            phone=phone,
            text=text,
            session=session,
            customer=customer,
            lang=lang,
            message_id=message_id,
            org_id=org_id,
            classification=classification,
            context=context,
            order=order,
        )
        result = AbuuSkillRouter.dispatch(turn)

        if result.action == "delegate_inbound":
            AbuuInboundService._send_reply(main_db, phone, unknown_message(lang), org_id=org_id)
            if session:
                session.last_message_id = message_id
                abuu_db.add(session)
            return {"handled": True, "action": "unknown"}

        if result.reply:
            AbuuInboundService._send_reply(main_db, phone, result.reply, org_id=org_id)
        if session:
            session.last_message_id = message_id
            abuu_db.add(session)

        payload = {
            "handled": result.handled,
            "action": result.action,
            "skill": result.skill,
            "next_step": result.next_step,
            "step": result.next_step,
        }
        payload.update(result.extra)
        if transcript_confidence is not None:
            payload["transcript_confidence"] = transcript_confidence
        return payload

    @staticmethod
    def _start_order(
        abuu_db: Session,
        main_db: Session,
        *,
        phone: str,
        customer,
        lang: str,
        message_id: str | None,
        org_id: str | None,
    ) -> dict[str, Any]:
        default_address = saved_address_summary(abuu_db, customer)
        lat = lng = None
        from app.abuu.services.location_service import get_default_address

        addr = get_default_address(abuu_db, customer.id)
        if addr and addr.latitude is not None and addr.longitude is not None:
            lat, lng = addr.latitude, addr.longitude
        restaurant = AbuuOrderDraftService.default_restaurant(abuu_db, lat=lat, lng=lng)
        if restaurant is None:
            AbuuInboundService._send_reply(
                main_db,
                phone,
                "لا توجد مطاعم متاحة حالياً." if lang == "ar" else "No restaurants are available right now.",
                org_id=org_id,
            )
            return {"handled": True, "reason": "no_restaurant"}

        order = AbuuOrderDraftService.start_draft(abuu_db, customer=customer, restaurant=restaurant)
        apply_saved_address_to_order(abuu_db, order, customer)
        context = {
            "restaurant_id": restaurant.id,
            "greeting_sent": False,
            "active_categories": [],
            "suggested_items": [],
        }
        if not customer.name:
            AbuuOrderDraftService.upsert_session(
                abuu_db,
                phone=phone,
                step="awaiting_name",
                context=context,
                active_order_id=order.id,
                message_id=message_id,
            )
            AbuuInboundService._send_reply(main_db, phone, ask_name_message(lang), org_id=org_id)
            return {"handled": True, "action": "started", "order_id": order.id, "step": "awaiting_name"}

        context["greeting_sent"] = True
        AbuuOrderDraftService.upsert_session(
            abuu_db,
            phone=phone,
            step="awaiting_preference",
            context=context,
            active_order_id=order.id,
            message_id=message_id,
        )
        AbuuInboundService._send_reply(
            main_db,
            phone,
            personalized_greeting_message(
                first_name=first_name(customer.name),
                lang=lang,
                saved_address=default_address,
            ),
            org_id=org_id,
        )
        return {"handled": True, "action": "started", "order_id": order.id, "step": "awaiting_preference"}

    @staticmethod
    def _try_preference_menu(
        abuu_db: Session,
        main_db: Session,
        *,
        phone: str,
        session,
        order: CustomerOrder | None,
        customer,
        text: str,
        context: dict,
        lang: str,
        message_id: str | None,
        org_id: str | None,
    ) -> dict[str, Any] | None:
        if session.step not in {"awaiting_preference", "browsing"}:
            return None
        pending = list(context.get("pending_categories") or [])
        categories = match_food_categories(text)
        if pending:
            overlap = [cat for cat in categories if cat in pending]
            if len(overlap) == 1:
                categories = overlap
            elif len(pending) == 1:
                categories = pending
        if not categories:
            return None
        if len(categories) > 1:
            context["pending_categories"] = categories
            AbuuOrderDraftService.upsert_session(
                abuu_db,
                phone=phone,
                step="awaiting_preference",
                context=context,
                active_order_id=session.active_order_id,
                message_id=message_id,
            )
            AbuuInboundService._send_reply(
                main_db,
                phone,
                category_clarification_message(categories, lang),
                org_id=org_id,
            )
            return {"handled": True, "action": "category_clarification"}

        restaurant_id = str(context.get("restaurant_id") or (order.restaurant_id if order else ""))
        restaurant = abuu_db.get(Restaurant, restaurant_id)
        if restaurant is None:
            return None
        for category in categories:
            remember_preference(customer, category=category)
        abuu_db.add(customer)
        items = AbuuOrderDraftService.list_menu_items(
            abuu_db,
            restaurant_id,
            categories=categories,
            customer=customer,
        )
        indexed = list(enumerate(items, start=1))
        context["active_categories"] = categories
        context["suggested_items"] = AbuuOrderDraftService.build_suggestion_index(items)
        context.pop("pending_categories", None)
        AbuuOrderDraftService.upsert_session(
            abuu_db,
            phone=phone,
            step="browsing",
            context=context,
            active_order_id=session.active_order_id,
            message_id=message_id,
        )
        AbuuInboundService._send_reply(
            main_db,
            phone,
            preference_menu_message(restaurant, indexed, categories=categories, lang=lang),
            org_id=org_id,
        )
        return {"handled": True, "action": "preference_menu", "categories": categories}

    @staticmethod
    def _handle_typed_address(
        abuu_db: Session,
        main_db: Session,
        *,
        phone: str,
        session,
        order: CustomerOrder | None,
        customer,
        text: str,
        context: dict,
        lang: str,
        message_id: str | None,
        org_id: str | None,
    ) -> dict[str, Any]:
        if order is None:
            AbuuInboundService._send_reply(main_db, phone, unknown_message(lang), org_id=org_id)
            return {"handled": True, "action": "no_order"}
        normalized = normalize_address_text(text)
        geocoded = forward_geocode(normalized)
        lat = geocoded.latitude if geocoded else None
        lng = geocoded.longitude if geocoded else None
        restaurant = abuu_db.get(Restaurant, order.restaurant_id)
        if restaurant and lat is not None and lng is not None:
            ok, distance = validate_delivery_radius(restaurant, lat=lat, lng=lng)
            if not ok:
                AbuuInboundService._send_reply(
                    main_db,
                    phone,
                    out_of_delivery_area_message(
                        lang,
                        distance_km=distance,
                        radius_km=float(restaurant.delivery_radius_km or 0),
                    ),
                    org_id=org_id,
                )
                return {"handled": True, "action": "out_of_delivery_area"}
        if geocoded is None:
            clarification_count = int(context.get("location_clarification_count") or 0)
            if clarification_count < 1 and not order.location_clarification_sent:
                context["location_clarification_count"] = clarification_count + 1
                order.location_clarification_sent = True
                order.location_missing = True
                abuu_db.add(order)
                AbuuOrderDraftService.upsert_session(
                    abuu_db,
                    phone=phone,
                    step="awaiting_delivery",
                    context=context,
                    active_order_id=order.id,
                    message_id=message_id,
                )
                AbuuInboundService._send_reply(main_db, phone, location_clarification_message(lang), org_id=org_id)
                AbuuEventIdempotencyService.begin_event(
                    abuu_db,
                    source="system",
                    event_type="geocode_failed",
                    idempotency_key=f"order:{order.id}:geocode:{payload_hash({'text': normalized})}",
                    order_id=order.id,
                    payload={"address_text": normalized},
                )
                return {"handled": True, "action": "geocode_failed"}
        address = save_customer_address(
            abuu_db,
            customer_id=customer.id,
            address_text=geocoded.display_name if geocoded else normalized,
            latitude=lat,
            longitude=lng,
            source_message_id=message_id,
        )
        order.delivery_address_id = address.id
        order.location_missing = False
        abuu_db.add(order)
        if context.get("confirm_after_address"):
            return AbuuInboundService._finalize_confirm(
                abuu_db, main_db, phone=phone, order=order, lang=lang, org_id=org_id, context=context
            )
        AbuuOrderDraftService.upsert_session(
            abuu_db,
            phone=phone,
            step="browsing",
            context=context,
            active_order_id=order.id,
            message_id=message_id,
        )
        AbuuInboundService._send_reply(main_db, phone, address_saved_message(lang), org_id=org_id)
        return {"handled": True, "action": "address_saved"}

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
            source_message_id=message_id,
        )
        order.delivery_address_id = address.id
        order.location_missing = False
        abuu_db.add(order)
        context = AbuuInboundService._load_context(session)
        if context.get("confirm_after_address"):
            return AbuuInboundService._finalize_confirm(
                abuu_db,
                main_db,
                phone=customer.phone,
                order=order,
                lang=lang,
                org_id=org_id,
                context=context,
            )
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
    def _finalize_confirm(
        abuu_db: Session,
        main_db: Session,
        *,
        phone: str,
        order: CustomerOrder,
        lang: str,
        org_id: str | None,
        context: dict | None = None,
    ) -> dict[str, Any]:
        fingerprint = AbuuOrderDraftService.cart_fingerprint(abuu_db, order)
        if order.status == "confirmed":
            AbuuInboundService._send_reply(main_db, phone, already_confirmed_message(lang), org_id=org_id)
            return {"handled": True, "action": "already_confirmed", "order_id": order.id}
        try:
            allergy_note = (context or {}).get("kitchen_allergy_note") if context else None
            AbuuOrderDraftService.confirm_draft(abuu_db, order, allergy_note=allergy_note)
        except ValueError as exc:
            AbuuInboundService._send_reply(main_db, phone, str(exc), org_id=org_id)
            return {"handled": True, "action": "confirm_failed", "detail": str(exc)}
        if context is not None:
            context["confirmed_cart_fingerprint"] = fingerprint
        AbuuOrderDraftService.clear_session(abuu_db, phone)
        if get_settings().yallasay_auto_send_on_confirm:
            try:
                AbuuOrderService.mark_paid_manual(abuu_db, order, confirmed_by="yallasay_whatsapp")
                reply = order_sent_to_restaurant_message(order, lang)
            except ValueError:
                reply = confirm_pending_payment_message(order, lang)
        else:
            reply = confirm_pending_payment_message(order, lang)
        AbuuInboundService._send_reply(main_db, phone, reply, org_id=org_id)
        return {"handled": True, "action": "confirmed", "order_id": order.id}

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
    def _should_use_orchestrator(session) -> bool:
        if not AbuuConversationOrchestrator.conversation_enabled():
            return False
        step = session.step if session else None
        if step in {"awaiting_substitution", "awaiting_name", "awaiting_delivery"}:
            return False
        return True

    @staticmethod
    def _run_orchestrator_turn(
        abuu_db: Session,
        main_db: Session,
        *,
        phone: str,
        text: str,
        session,
        customer=None,
        lang: str = "ar",
        message_id: str | None,
        org_id: str | None,
    ) -> dict[str, Any]:
        result = AbuuConversationOrchestrator.handle(
            abuu_db,
            main_db,
            phone=phone,
            text=text,
            message_id=message_id,
            org_id=org_id,
        )
        if result.get("action") == "delegate_confirm":
            order = (
                abuu_db.get(CustomerOrder, session.active_order_id)
                if session and session.active_order_id
                else None
            )
            if order is None:
                from app.abuu.agent.session import load_session

                agent_session = load_session(abuu_db, phone)
                if agent_session.active_order_id:
                    order = abuu_db.get(CustomerOrder, agent_session.active_order_id)
            if order is not None:
                context = AbuuInboundService._load_context(session) if session else {}
                return AbuuInboundService._finalize_confirm(
                    abuu_db,
                    main_db,
                    phone=phone,
                    order=order,
                    lang=lang,
                    org_id=org_id,
                    context=context,
                )
        if result.get("action") == "cancelled":
            AbuuInboundService._send_reply(main_db, phone, cancel_message(lang), org_id=org_id)
            if session:
                session.last_message_id = message_id
                abuu_db.add(session)
            return {"handled": True, "action": "cancelled", "intent": result.get("intent")}

        reply = result.get("reply")
        if reply:
            AbuuInboundService._send_reply(main_db, phone, reply, org_id=org_id)
        if session:
            session.last_message_id = message_id
            abuu_db.add(session)
        return result

    @staticmethod
    def _should_use_legacy_text_flow(text: str, session) -> bool:
        """Deterministic menu/greeting flow — avoids agent ack with no follow-up."""
        step = session.step if session else None
        has_session = bool(session and step not in {"", "idle", None})
        if is_abuu_start_message(text):
            return True
        intent = detect_intent(text, has_active_session=has_session, step=step)
        if intent.name == "menu":
            return True
        if step in {"awaiting_name", "awaiting_preference", "browsing", "awaiting_delivery", "awaiting_substitution"}:
            return True
        return False

    @staticmethod
    def _should_use_voice_agent(main_db: Session) -> bool:
        """Voice notes use the LLM agent whenever DeepSeek is configured."""
        return _deepseek_platform_ready(main_db)

    @staticmethod
    def _should_use_agent_text_flow(main_db: Session, text: str, session) -> bool:
        if not get_settings().abuu_agent_enabled:
            return False
        if AbuuInboundService._should_use_legacy_text_flow(text, session):
            return False
        return _deepseek_platform_ready(main_db)

    @staticmethod
    def _send_agent_ack(main_db: Session, to_phone: str, lang: str, *, org_id: str | None) -> None:
        body = "وصلت رسالتك، لحظة..." if lang == "ar" else "Got it, one moment..."
        AbuuInboundService._send_reply(main_db, to_phone, body, org_id=org_id)

    @staticmethod
    def _send_reply(main_db: Session, to_phone: str, body: str, *, org_id: str | None) -> None:
        reply_text = wa_customer_sanitize(body)
        result = TelnyxMessagingService.send_whatsapp(
            main_db,
            to_number=to_phone,
            body=reply_text,
            org_id=org_id,
            meter_usage=False,
        )
        logger.info(
            "abuu_wa_trace OUT to=%s ok=%s body=%r",
            to_phone,
            result.ok,
            reply_text[:300],
        )
        if not result.ok:
            logger.warning("abuu_wa_reply_failed to=%s status=%s detail=%s", to_phone, result.status, result.detail)
