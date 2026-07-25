"""Expo WhatsApp channel adapter — trigger scan, relay Q&A over WhatsApp, hybrid offer messages.

The actual conversation state machine (steps, hybrid asset matching, scoring) lives in
session_flow_service.ExpoSessionFlowService so it can be shared with the public web fallback.
This module only: parses inbound WhatsApp text, drives that engine, and turns its plain-data
results into WhatsApp messages.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.expo import ExpoBooth, ExpoSession
from app.services.expo.booth_service import ExpoBoothService, find_expo_token_in_text
from app.services.expo.offer_delivery_service import deliver_asset_link_message, format_asset_list_message
from app.services.expo.session_flow_service import ExpoSessionFlowService
from app.services.telnyx_messaging_service import TelnyxMessagingService

logger = logging.getLogger(__name__)

STOP_WORDS = frozenset({"stop", "unsubscribe", "cancel", "opt out", "opt-out", "end", "quit"})
STOP_ACK_MESSAGE = "You've been unsubscribed. Thanks again for visiting our stand!"
UNKNOWN_QR_MESSAGE = (
    "Thanks for messaging us! This Expo QR code is not active yet. "
    "Please ask the stand team for a fresh QR, or try again after the organiser activates Expo."
)


class ExpoWhatsappService:
    @staticmethod
    def try_handle_inbound(
        db: Session,
        *,
        from_phone: str,
        body: str,
        org_id: str | None = None,
        record: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del record  # voice-note capture is not implemented for Expo yet
        phone = str(from_phone or "").strip()
        text = str(body or "").strip()
        if not phone:
            return {"handled": False, "reason": "missing_from"}

        lower = text.lower().strip()
        if lower in STOP_WORDS:
            session = ExpoSessionFlowService.find_active_session(db, visitor_phone=phone)
            if session is None:
                return {"handled": False, "reason": "no_session"}
            ExpoSessionFlowService.stop(db, session=session)
            ExpoWhatsappService._send(db, to_number=phone, body=STOP_ACK_MESSAGE, org_id=session.org_id)
            return {"handled": True, "opted_out": True, "session_id": session.id, "org_id": session.org_id}

        token = find_expo_token_in_text(db, text)
        booth = ExpoBoothService.find_by_token(db, token) if token else None
        if token and booth is None:
            logger.warning("expo_wa_token_not_found token=%s from=%s", token, phone)
            if "visited" in lower or "exhibition" in lower or "stand" in lower:
                ExpoWhatsappService._send(db, to_number=phone, body=UNKNOWN_QR_MESSAGE, org_id=org_id)
                return {"handled": True, "reason": "booth_not_found", "token": token}
            return {"handled": False, "reason": "booth_not_found", "token": token}

        if booth is not None:
            if str(booth.status or "").lower() != "active":
                ExpoWhatsappService._send(
                    db,
                    to_number=phone,
                    body="This Expo booth is paused. Please ask the stand team for help.",
                    org_id=booth.org_id,
                )
                return {"handled": True, "reason": "booth_paused", "booth_id": booth.id, "org_id": booth.org_id}
            result = ExpoSessionFlowService.start_session(db, booth=booth, channel="whatsapp", visitor_phone=phone)
            prompt = str(result.get("prompt") or "").strip()
            sent = ExpoWhatsappService._send(db, to_number=phone, body=prompt, org_id=booth.org_id)
            logger.info(
                "expo_wa_session_started booth_id=%s session_id=%s sent=%s",
                booth.id,
                result.get("session_id"),
                sent,
            )
            return {
                "handled": True,
                "session_id": result.get("session_id"),
                "org_id": booth.org_id,
                "booth_id": booth.id,
                "sent": sent,
            }

        session = ExpoSessionFlowService.find_active_session(db, visitor_phone=phone)
        if session is None:
            return {"handled": False, "reason": "no_session"}

        result = ExpoSessionFlowService.advance(db, session=session, answer=text, answer_source="text")
        ExpoWhatsappService._relay(db, session=session, result=result)
        return {
            "handled": True,
            "session_id": session.id,
            "org_id": session.org_id,
            "done": bool(result.get("done")),
        }

    @staticmethod
    def _relay(db: Session, *, session: ExpoSession, result: dict[str, Any]) -> None:
        booth = db.get(ExpoBooth, session.booth_id)
        booth_token = booth.qr_token if booth else ""

        for asset in result.get("assets") or []:
            ExpoWhatsappService._send(
                db,
                to_number=session.visitor_phone,
                body=deliver_asset_link_message(asset, booth_token),
                org_id=session.org_id,
            )

        if result.get("awaiting_pick"):
            prefix = "Sorry, I didn't catch that.\n\n" if result.get("retry") else ""
            ExpoWhatsappService._send(
                db,
                to_number=session.visitor_phone,
                body=prefix + format_asset_list_message(result.get("candidates") or []),
                org_id=session.org_id,
            )
            return

        prompt = str(result.get("prompt") or "").strip()
        if prompt:
            ExpoWhatsappService._send(db, to_number=session.visitor_phone, body=prompt, org_id=session.org_id)

    @staticmethod
    def _send(db: Session, *, to_number: str, body: str, org_id: str | None) -> bool:
        clean = str(body or "").strip()
        if not clean:
            return False
        # Try expo profile first; fall back if expo isn't on the connection profile yet.
        for code in ("expo", "customer_feedback", None):
            result = TelnyxMessagingService.send_whatsapp(
                db,
                to_number=to_number,
                body=clean,
                org_id=org_id,
                meter_usage=False,
                service_code=code,
            )
            if result.ok:
                return True
            logger.warning(
                "expo_wa_send_failed to=%s service_code=%s status=%s detail=%s org_id=%s",
                to_number,
                code,
                result.status,
                result.detail,
                org_id,
            )
        return False
