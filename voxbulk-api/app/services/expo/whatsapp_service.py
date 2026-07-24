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
from app.services.expo.booth_service import ExpoBoothService, extract_expo_token
from app.services.expo.offer_delivery_service import deliver_asset_link_message, format_asset_list_message
from app.services.expo.session_flow_service import ExpoSessionFlowService
from app.services.telnyx_messaging_service import TelnyxMessagingService

logger = logging.getLogger(__name__)

STOP_WORDS = frozenset({"stop", "unsubscribe", "cancel", "opt out", "opt-out", "end", "quit"})
STOP_ACK_MESSAGE = "You've been unsubscribed. Thanks again for visiting our stand!"


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

        token = extract_expo_token(text)
        booth = ExpoBoothService.find_by_token(db, token) if token else None
        if booth is not None:
            result = ExpoSessionFlowService.start_session(db, booth=booth, channel="whatsapp", visitor_phone=phone)
            ExpoWhatsappService._send(db, to_number=phone, body=str(result.get("prompt") or ""), org_id=booth.org_id)
            return {
                "handled": True,
                "session_id": result.get("session_id"),
                "org_id": booth.org_id,
                "booth_id": booth.id,
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

    # ------------------------------------------------------------------
    # Turn the engine's plain-data result into WhatsApp message(s)
    # ------------------------------------------------------------------

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
        result = TelnyxMessagingService.send_whatsapp(
            db,
            to_number=to_number,
            body=clean,
            org_id=org_id,
            meter_usage=False,
            service_code="expo",
        )
        if not result.ok:
            logger.warning(
                "expo_wa_send_failed to=%s status=%s detail=%s org_id=%s",
                to_number,
                result.status,
                result.detail,
                org_id,
            )
        return bool(result.ok)
