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


def looks_like_smart_card_message(text: str) -> bool:
    lower = str(text or "").lower()
    return "smart card" in lower or "smart-card" in lower or "smartcard" in lower


def find_smart_card_token_in_text(db: Session, text: str) -> str | None:
    """Return an active Smart Card qr_token present in the inbound message."""
    raw = str(text or "")
    candidates: list[str] = []
    for m in _TOKEN_RE.finditer(raw):
        tok = m.group(1)
        if tok not in candidates:
            candidates.append(tok)
    # Also accept "Ref: token" without word-boundary quirks
    m_ref = re.search(r"(?i)\bref\s*[:#]?\s*([a-z0-9]+-[a-z0-9]+-[a-f0-9]{16})\b", raw)
    if m_ref:
        tok = m_ref.group(1)
        if tok not in candidates:
            candidates.insert(0, tok)
    for token in candidates:
        rep = db.execute(
            select(SmartCardRepresentative).where(SmartCardRepresentative.qr_token == token)
        ).scalar_one_or_none()
        if rep is not None and str(rep.status or "") == "active":
            return token
    # Slow path: known tokens contained in message
    if looks_like_smart_card_message(raw):
        rows = db.execute(select(SmartCardRepresentative.qr_token).where(SmartCardRepresentative.status == "active")).scalars().all()
        lower = raw.lower()
        for tok in rows:
            t = str(tok or "").strip()
            if t and t.lower() in lower:
                return t
    return None


def build_smart_card_wa_trigger(*, rep_name: str, qr_token: str) -> str:
    """Friendly prefilled WhatsApp text — token kept as Ref: for routing."""
    name = str(rep_name or "our team").strip() or "our team"
    token = str(qr_token or "").strip()
    return (
        f"Hi — I scanned {name}'s Smart Card and would like to connect.\n"
        f"Ref: {token}"
    )


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

        # Voice note while in an active Smart Card session
        from app.services.smart_card.voice_note_service import is_audio_inbound, process_voice_for_session

        if is_audio_inbound(record if isinstance(record, dict) else None) and not text:
            voice_session = SmartCardWhatsappService.find_active_session(db, visitor_phone=phone)
            if voice_session is not None:
                SmartCardWhatsappService._send(
                    db,
                    to_number=phone,
                    body="Got your voice note — translating…",
                    org_id=voice_session.org_id,
                    from_number=reply_from,
                )
                voice = process_voice_for_session(
                    db,
                    session=voice_session,
                    record=record if isinstance(record, dict) else None,
                )
                if not voice.get("ok"):
                    SmartCardWhatsappService._send(
                        db,
                        to_number=phone,
                        body="Sorry — I couldn't hear that clearly. Please type your answer, or send the voice note again.",
                        org_id=voice_session.org_id,
                        from_number=reply_from,
                    )
                    return {
                        "handled": True,
                        "reason": "voice_failed",
                        "sent": True,
                        "session_id": voice_session.id,
                        "org_id": voice_session.org_id,
                    }
                answer = str(voice.get("answer_text_en") or voice.get("original_text") or "").strip()
                try:
                    result = SmartCardSessionFlowService.advance(
                        db,
                        session=voice_session,
                        answer=answer,
                        answer_source="voice",
                        original_text=str(voice.get("original_text") or "") or None,
                        answer_text_en=str(voice.get("answer_text_en") or "") or None,
                        voice_job_id=str(voice.get("job_id") or "") or None,
                    )
                    db.commit()
                except SmartCardSessionError as e:
                    db.rollback()
                    msg = str(e).replace("_", " ")
                    SmartCardWhatsappService._send(
                        db,
                        to_number=phone,
                        body=msg,
                        org_id=voice_session.org_id,
                        from_number=reply_from,
                    )
                    return {"handled": True, "reason": str(e), "sent": True, "session_id": voice_session.id}
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
                        org_id=voice_session.org_id,
                        from_number=reply_from,
                    )
                return {
                    "handled": True,
                    "reason": "voice_completed" if result.get("done") else "voice_advanced",
                    "sent": sent,
                    "session_id": voice_session.id,
                    "org_id": voice_session.org_id,
                }

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
