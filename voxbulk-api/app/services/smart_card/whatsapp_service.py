"""Smart Card QR WhatsApp inbound — plain session text (shared flow with web)."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.smart_card import SmartCardRepresentative, SmartCardSession
from app.services.smart_card.session_flow_service import SmartCardSessionError, SmartCardSessionFlowService
from app.services.telnyx_messaging_service import TelnyxMessagingService

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"\b([a-z0-9]+-[a-z0-9]+-[a-f0-9]{16})\b", re.I)
STOP_WORDS = frozenset({"stop", "unsubscribe", "cancel", "opt out", "opt-out", "end", "quit"})


def find_smart_card_token_in_text(db: Session, text: str) -> str | None:
    for m in _TOKEN_RE.finditer(text or ""):
        token = m.group(1)
        rep = db.execute(
            select(SmartCardRepresentative).where(SmartCardRepresentative.qr_token == token)
        ).scalar_one_or_none()
        if rep is not None and str(rep.status or "") == "active":
            return token
    return None


class SmartCardWhatsappService:
    @staticmethod
    def find_active_session(db: Session, *, visitor_phone: str) -> SmartCardSession | None:
        phone = str(visitor_phone or "").strip()
        if not phone:
            return None
        return (
            db.execute(
                select(SmartCardSession)
                .where(
                    SmartCardSession.visitor_phone == phone,
                    SmartCardSession.status == "active",
                    SmartCardSession.channel == "whatsapp",
                )
                .order_by(SmartCardSession.created_at.desc())
                .limit(1)
            )
            .scalar_one_or_none()
        )

    @staticmethod
    def _is_image_inbound(record: dict[str, Any] | None) -> bool:
        if not isinstance(record, dict):
            return False
        msg_type = str(record.get("type") or record.get("message_type") or "").strip().lower()
        if msg_type in {"image", "photo", "sticker"}:
            return True
        if isinstance(record.get("image"), dict):
            return True
        content = record.get("content") if isinstance(record.get("content"), dict) else {}
        if str(content.get("type") or "").lower() == "image":
            return True
        media = record.get("media") or record.get("medias") or []
        if isinstance(media, list):
            for item in media:
                if not isinstance(item, dict):
                    continue
                ct = str(item.get("content_type") or item.get("mime_type") or "").lower()
                if ct.startswith("image/"):
                    return True
        return False

    @staticmethod
    def try_handle_inbound(
        db: Session,
        *,
        from_phone: str,
        body: str,
        org_id: str | None = None,
        record: dict[str, Any] | None = None,
        business_number: str | None = None,
    ) -> dict[str, Any]:
        phone = str(from_phone or "").strip()
        text = str(body or "").strip()
        reply_from = str(business_number or "").strip() or None
        if not phone:
            return {"handled": False, "reason": "missing_from"}

        if text.lower() in STOP_WORDS:
            active = SmartCardWhatsappService.find_active_session(db, visitor_phone=phone)
            if active is not None:
                active.status = "stopped"
                db.add(active)
                db.commit()
                SmartCardWhatsappService._send(
                    db,
                    to_number=phone,
                    body="You've been unsubscribed. Thanks for chatting.",
                    org_id=active.org_id,
                    from_number=reply_from,
                )
                return {"handled": True, "reason": "stopped", "sent": True}
            return {"handled": False, "reason": "no_session"}

        token = find_smart_card_token_in_text(db, text)
        active = SmartCardWhatsappService.find_active_session(db, visitor_phone=phone)

        try:
            if token:
                rep = db.execute(
                    select(SmartCardRepresentative).where(SmartCardRepresentative.qr_token == token)
                ).scalar_one_or_none()
                if rep is None:
                    return {"handled": False, "reason": "token_not_found"}
                if org_id and rep.org_id != org_id:
                    # Allow when webhook org differs; prefer rep's org for routing
                    pass
                if active is not None:
                    active.status = "superseded"
                    db.add(active)
                result = SmartCardSessionFlowService.start_session(
                    db, rep=rep, channel="whatsapp", visitor_phone=phone
                )
                db.commit()
                session = db.get(SmartCardSession, result["session_id"])
                prompt = str(result.get("prompt") or "").strip()
                sent = False
                if prompt and session is not None:
                    sent = SmartCardWhatsappService._send(
                        db,
                        to_number=phone,
                        body=prompt,
                        org_id=session.org_id,
                        from_number=reply_from,
                    )
                return {
                    "handled": True,
                    "reason": "started",
                    "sent": sent,
                    "session_id": result.get("session_id"),
                    "org_id": rep.org_id,
                }

            if active is None:
                return {"handled": False, "reason": "no_session"}

            if SmartCardWhatsappService._is_image_inbound(record) and (active.current_step or "") == "contact":
                from app.services.expo.business_card_ocr_service import ExpoBusinessCardService

                fields = ExpoBusinessCardService.extract_from_inbound(db, record)
                ocr = SmartCardSessionFlowService.apply_card_ocr(
                    db,
                    session=active,
                    name=fields.get("name"),
                    company=fields.get("company"),
                    email=fields.get("email"),
                    phone=fields.get("phone"),
                )
                db.commit()
                sent = SmartCardWhatsappService._send(
                    db,
                    to_number=phone,
                    body=str(ocr.get("prompt") or "Please confirm your details."),
                    org_id=active.org_id,
                    from_number=reply_from,
                )
                return {
                    "handled": True,
                    "reason": "ocr",
                    "sent": sent,
                    "session_id": active.id,
                    "org_id": active.org_id,
                }

            result = SmartCardSessionFlowService.advance(db, session=active, answer=text)
            db.commit()
            reply = (
                str(result.get("message") or result.get("prompt") or "").strip()
                if result.get("done")
                else str(result.get("prompt") or "").strip()
            )
            sent = False
            if reply:
                sent = SmartCardWhatsappService._send(
                    db,
                    to_number=phone,
                    body=reply,
                    org_id=active.org_id,
                    from_number=reply_from,
                )
            return {
                "handled": True,
                "reason": "completed" if result.get("done") else "advanced",
                "sent": sent,
                "session_id": active.id,
                "org_id": active.org_id,
            }
        except SmartCardSessionError as e:
            db.rollback()
            msg = str(e).replace("_", " ")
            if active is not None or token:
                SmartCardWhatsappService._send(
                    db,
                    to_number=phone,
                    body=msg,
                    org_id=(active.org_id if active else org_id),
                    from_number=reply_from,
                )
                return {"handled": True, "reason": str(e), "sent": True}
            return {"handled": False, "reason": str(e)}
        except Exception:
            logger.exception("smart_card_wa_inbound_failed")
            db.rollback()
            return {"handled": False, "reason": "error"}

    @staticmethod
    def _send(
        db: Session,
        *,
        to_number: str,
        body: str,
        org_id: str | None,
        from_number: str | None = None,
    ) -> bool:
        clean = str(body or "").strip()
        if not clean:
            return False
        for code in ("smart_card", "customer_feedback", None):
            result = TelnyxMessagingService.send_whatsapp(
                db,
                to_number=to_number,
                body=clean,
                from_number=from_number,
                org_id=org_id,
                meter_usage=False,
                service_code=code,
                template_name=None,
                template_id=None,
                template_language=None,
                template_components=None,
            )
            if result.ok:
                logger.info(
                    "smart_card_wa_sent to=%s service_code=%s org_id=%s",
                    to_number,
                    code,
                    org_id,
                )
                return True
            logger.warning(
                "smart_card_wa_send_failed to=%s service_code=%s status=%s detail=%s",
                to_number,
                code,
                result.status,
                result.detail,
            )
        return False
