"""Expo WhatsApp channel adapter — trigger scan, relay Q&A over WhatsApp, hybrid offer messages.

The actual conversation state machine (steps, hybrid asset matching, scoring) lives in
session_flow_service.ExpoSessionFlowService so it can be shared with the public web fallback.
This module only: parses inbound WhatsApp text, drives that engine, and turns its plain-data
results into WhatsApp messages.
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.expo import ExpoBooth, ExpoLead, ExpoSession
from app.services.expo.booth_service import (
    BOOTH_CLOSED_MESSAGE,
    ExpoBoothService,
    booth_access_block_reason,
    booth_is_expired,
    find_expo_token_in_text,
)
from app.services.expo.offer_delivery_service import (
    asset_public_url,
    deliver_asset_link_message,
    format_asset_list_message,
)
from app.services.expo.question_bank import POST_COMPLETE_HANDOFF, get_template_prompt
from app.services.expo.session_flow_service import ExpoSessionFlowService
from app.services.telnyx_messaging_service import TelnyxMessagingService

logger = logging.getLogger(__name__)

_DOCUMENT_KINDS = frozenset({"pdf", "spreadsheet", "document", "excel", "xls", "xlsx", "csv"})
_DOCUMENT_EXTS = (".pdf", ".xls", ".xlsx", ".csv", ".doc", ".docx")


def _asset_has_stored_file(asset: dict[str, Any]) -> bool:
    return bool(str(asset.get("storage_path") or "").strip())


def _asset_supports_document_send(asset: dict[str, Any]) -> bool:
    """True when WhatsApp should get a document bubble (file), not a pasted URL."""
    path_blob = " ".join(
        [
            str(asset.get("storage_path") or ""),
            str(asset.get("original_filename") or ""),
        ]
    ).lower()
    if any(path_blob.endswith(ext) or ext in path_blob for ext in _DOCUMENT_EXTS):
        return True
    # Non-document uploads (e.g. video) must not be forced as documents.
    if path_blob and any(path_blob.endswith(ext) for ext in (".mp4", ".mov", ".webm", ".png", ".jpg", ".jpeg", ".gif")):
        return False
    kind = str(asset.get("kind") or "").strip().lower()
    if kind in _DOCUMENT_KINDS:
        return True
    if _asset_has_stored_file(asset) and kind not in {"video", "image", "audio", "link"}:
        return True
    blob = " ".join(
        [
            str(asset.get("external_url") or ""),
            str(asset.get("title") or ""),
        ]
    ).lower()
    return any(blob.endswith(ext) or ext in blob for ext in _DOCUMENT_EXTS)


def _wa_document_url(url: str) -> str:
    """Strip tracking query params — Meta/Telnyx fetch the file more reliably on a clean path."""
    raw = str(url or "").strip()
    if not raw.startswith("http"):
        return raw
    parts = urlsplit(raw)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _asset_document_filename(asset: dict[str, Any]) -> str:
    for key in ("original_filename", "storage_path", "title", "asset_key"):
        raw = str(asset.get(key) or "").strip()
        if not raw:
            continue
        name = Path(raw.replace("\\", "/")).name
        if "." in name:
            return name[:240]
        kind = str(asset.get("kind") or "").lower()
        if kind in {"spreadsheet", "excel", "xls", "xlsx", "csv"}:
            return f"{name[:200]}.xlsx"
        return f"{name[:200]}.pdf"
    return "document.pdf"

STOP_WORDS = frozenset({"stop", "unsubscribe", "cancel", "opt out", "opt-out", "end", "quit"})
STOP_ACK_MESSAGE = "You've been unsubscribed. Thanks again for visiting our stand!"
UNKNOWN_QR_MESSAGE = (
    "Thanks for messaging us! This Expo QR code is not active yet. "
    "Please ask the stand team for a fresh QR, or try again after the organiser activates Expo."
)


def _looks_like_smart_card_inbound(text: str) -> bool:
    """Shared WA line — never treat Smart Card QR opens as Expo."""
    lower = str(text or "").lower()
    return "smart card" in lower or "smart-card" in lower or "smartcard" in lower


class ExpoWhatsappService:
    @staticmethod
    def _is_image_inbound(record: dict[str, Any] | None) -> bool:
        if not isinstance(record, dict):
            return False
        msg_type = str(record.get("type") or record.get("message_type") or "").strip().lower()
        if msg_type in {"image", "photo", "sticker"}:
            return True
        if isinstance(record.get("image"), dict):
            return True
        # Telnyx nested shapes
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
        # Reply on the same WhatsApp business line the visitor messaged (QR uses CF number).
        reply_from = str(business_number or "").strip() or None
        if not phone:
            return {"handled": False, "reason": "missing_from"}

        # Smart Card shares this WA line — leave those messages for SmartCardWhatsappService.
        if _looks_like_smart_card_inbound(text):
            return {"handled": False, "reason": "smart_card_message"}

        # Voice note while in an active Expo session
        from app.services.expo.voice_note_service import is_audio_inbound, process_voice_for_session

        if is_audio_inbound(record if isinstance(record, dict) else None) and not text:
            session = ExpoSessionFlowService.find_active_session(db, visitor_phone=phone)
            if session is not None:
                ExpoWhatsappService._send(
                    db,
                    to_number=phone,
                    body="Got your voice note — translating…",
                    org_id=session.org_id,
                    from_number=reply_from,
                )
                voice = process_voice_for_session(
                    db,
                    session=session,
                    record=record if isinstance(record, dict) else None,
                )
                if not voice.get("ok"):
                    ExpoWhatsappService._send(
                        db,
                        to_number=phone,
                        body="Sorry — I couldn't hear that clearly. Please type your answer, or send the voice note again.",
                        org_id=session.org_id,
                        from_number=reply_from,
                    )
                    return {
                        "handled": True,
                        "session_id": session.id,
                        "org_id": session.org_id,
                        "via": "voice_failed",
                    }
                result = ExpoSessionFlowService.advance(
                    db,
                    session=session,
                    answer=str(voice.get("answer_text_en") or ""),
                    answer_source="voice",
                    original_text=str(voice.get("original_text") or ""),
                    answer_text_en=str(voice.get("answer_text_en") or ""),
                    detected_language=voice.get("detected_language"),
                    voice_job_id=voice.get("job_id"),
                )
                ExpoWhatsappService._relay(db, session=session, result=result, from_number=reply_from)
                return {
                    "handled": True,
                    "session_id": session.id,
                    "org_id": session.org_id,
                    "via": "voice",
                }

        # Business-card photo while in an active Expo session (process even with a caption —
        # a caption like "here's my card" must not skip OCR).
        image_inbound = ExpoWhatsappService._is_image_inbound(record if isinstance(record, dict) else None)
        if image_inbound:
            session = ExpoSessionFlowService.find_active_session(db, visitor_phone=phone)
            if session is not None:
                from app.services.expo.business_card_ocr_service import ExpoBusinessCardService

                fields, card_path = ExpoBusinessCardService.save_inbound_image(
                    db,
                    org_id=session.org_id,
                    booth_id=session.booth_id,
                    record=record if isinstance(record, dict) else None,
                )
                result = ExpoSessionFlowService.advance(
                    db,
                    session=session,
                    answer="[business card image]",
                    answer_source="image",
                    contact_fields=fields or None,
                    business_card_path=card_path,
                )
                ExpoWhatsappService._relay(db, session=session, result=result, from_number=reply_from)
                return {
                    "handled": True,
                    "session_id": session.id,
                    "org_id": session.org_id,
                    "via": "business_card",
                    "card_fields": fields or None,
                }

        lower = text.lower().strip()
        if lower in STOP_WORDS:
            session = ExpoSessionFlowService.find_active_session(db, visitor_phone=phone)
            if session is None:
                return {"handled": False, "reason": "no_session"}
            ExpoSessionFlowService.stop(db, session=session)
            ExpoWhatsappService._send(
                db,
                to_number=phone,
                body=STOP_ACK_MESSAGE,
                org_id=session.org_id,
                from_number=reply_from,
            )
            return {"handled": True, "opted_out": True, "session_id": session.id, "org_id": session.org_id}

        token = find_expo_token_in_text(db, text)
        booth = ExpoBoothService.find_by_token(db, token) if token else None
        if token and booth is None:
            logger.warning(
                "expo_wa_token_not_found token_prefix=%s from_hash=%s",
                str(token)[:12],
                hashlib.sha256(str(phone or "").encode("utf-8")).hexdigest()[:12],
            )
            ExpoWhatsappService._send(
                db,
                to_number=phone,
                body=UNKNOWN_QR_MESSAGE,
                org_id=org_id,
                from_number=reply_from,
            )
            return {"handled": True, "reason": "booth_not_found", "token": token}

        if booth is not None:
            block = booth_access_block_reason(booth)
            if block:
                ExpoWhatsappService._send(
                    db,
                    to_number=phone,
                    body=block,
                    org_id=booth.org_id,
                    from_number=reply_from,
                )
                return {"handled": True, "reason": "booth_blocked", "booth_id": booth.id, "org_id": booth.org_id}
            if str(booth.status or "").lower() != "active":
                ExpoWhatsappService._send(
                    db,
                    to_number=phone,
                    body="This Expo booth is paused. Please ask the stand team for help.",
                    org_id=booth.org_id,
                    from_number=reply_from,
                )
                return {"handled": True, "reason": "booth_paused", "booth_id": booth.id, "org_id": booth.org_id}
            try:
                result = ExpoSessionFlowService.start_session(
                    db, booth=booth, channel="whatsapp", visitor_phone=phone
                )
            except ValueError as e:
                ExpoWhatsappService._send(
                    db,
                    to_number=phone,
                    body=str(e) or BOOTH_CLOSED_MESSAGE,
                    org_id=booth.org_id,
                    from_number=reply_from,
                )
                return {"handled": True, "reason": "booth_blocked", "booth_id": booth.id, "org_id": booth.org_id}
            prompt = str(result.get("prompt") or "").strip()
            sent = ExpoWhatsappService._send(
                db,
                to_number=phone,
                body=prompt,
                org_id=booth.org_id,
                from_number=reply_from,
            )
            logger.info(
                "expo_wa_session_started booth_id=%s session_id=%s superseded=%s sent=%s from_line=%s",
                booth.id,
                result.get("session_id"),
                result.get("superseded_sessions"),
                sent,
                reply_from,
            )
            if not sent:
                logger.error(
                    "expo_wa_first_reply_failed booth_id=%s session_id=%s to=%s from_line=%s",
                    booth.id,
                    result.get("session_id"),
                    phone,
                    reply_from,
                )
            return {
                "handled": True,
                "session_id": result.get("session_id"),
                "org_id": booth.org_id,
                "booth_id": booth.id,
                "superseded_sessions": result.get("superseded_sessions"),
                "sent": sent,
            }

        session = ExpoSessionFlowService.find_active_session(db, visitor_phone=phone)
        if session is None:
            # Likely Expo QR text without a matching token (edited draft / old QR).
            if (
                ("visited" in lower or "scanned" in lower or "catalogue" in lower or "questionnaire" in lower)
                and ("stand" in lower or "booth" in lower or "exhibition" in lower or " at " in lower or "qr" in lower)
            ):
                ExpoWhatsappService._send(
                    db,
                    to_number=phone,
                    body=UNKNOWN_QR_MESSAGE,
                    org_id=org_id,
                    from_number=reply_from,
                )
                return {"handled": True, "reason": "expo_like_no_token"}

            # Visitor already completed a booth chat recently and is messaging again on the
            # shared WA line — log the note against that lead and hand off, don't re-open the flow.
            if text:
                completed_session = ExpoSessionFlowService.find_recent_completed_session(
                    db, visitor_phone=phone
                )
                if completed_session is not None:
                    completed_lead = ExpoSessionFlowService._lead_for_session(db, completed_session)
                    ExpoSessionFlowService.record_post_complete_question(
                        db, session=completed_session, lead=completed_lead, text=text
                    )
                    ExpoWhatsappService._send(
                        db,
                        to_number=phone,
                        body=get_template_prompt(db, "post_complete_handoff", POST_COMPLETE_HANDOFF),
                        org_id=completed_session.org_id,
                        from_number=reply_from,
                    )
                    return {
                        "handled": True,
                        "reason": "post_complete_handoff",
                        "session_id": completed_session.id,
                        "org_id": completed_session.org_id,
                    }
            return {"handled": False, "reason": "no_session"}

        result = ExpoSessionFlowService.advance(db, session=session, answer=text, answer_source="text")
        ExpoWhatsappService._relay(db, session=session, result=result, from_number=reply_from)
        return {
            "handled": True,
            "session_id": session.id,
            "org_id": session.org_id,
            "done": bool(result.get("done")),
        }

    @staticmethod
    def _relay(
        db: Session,
        *,
        session: ExpoSession,
        result: dict[str, Any],
        from_number: str | None = None,
    ) -> None:
        booth = db.get(ExpoBooth, session.booth_id)
        booth_token = booth.qr_token if booth else ""
        lead = db.execute(select(ExpoLead).where(ExpoLead.session_id == session.id)).scalar_one_or_none()
        lead_id = str(lead.id).strip() if lead else None

        # Fresh consent picks only — never re-send historical files on thank-you / voice close.
        deliver_now = bool(result.get("deliver_now"))
        assets = [a for a in (result.get("assets") or []) if isinstance(a, dict)] if deliver_now else []

        if assets:
            n = len(assets)
            ExpoWhatsappService._send(
                db,
                to_number=session.visitor_phone,
                body=f"📎 Sending {'your file' if n == 1 else f'your {n} files'} now…",
                org_id=session.org_id,
                from_number=from_number,
            )
            for asset in assets:
                ExpoWhatsappService._send_asset(
                    db,
                    to_number=session.visitor_phone,
                    asset=asset,
                    booth_token=booth_token,
                    lead_id=lead_id,
                    org_id=session.org_id,
                    from_number=from_number,
                )
            # WhatsApp often delivers text before document media finishes processing.
            # Brief pause keeps the next question / closing after the files.
            time.sleep(1.5)

        if result.get("awaiting_pick"):
            prefix = "Sorry, I didn't catch that.\n\n" if result.get("retry") else ""
            ExpoWhatsappService._send(
                db,
                to_number=session.visitor_phone,
                body=prefix + format_asset_list_message(result.get("candidates") or []),
                org_id=session.org_id,
                from_number=from_number,
            )
            return

        # Closing: company card → save-contact vCard → thank-you (no separate logo document).
        pre_messages = result.get("pre_thank_you_messages")
        if not pre_messages and result.get("company_card"):
            pre_messages = [result["company_card"]]
        for msg in pre_messages or []:
            text = str(msg or "").strip()
            if not text:
                continue
            ExpoWhatsappService._send(
                db,
                to_number=session.visitor_phone,
                body=text,
                org_id=session.org_id,
                from_number=from_number,
            )

        vcard = result.get("vcard_document") if isinstance(result.get("vcard_document"), dict) else None
        if vcard:
            vurl = str(vcard.get("url") or "").strip()
            if vurl.startswith("http"):
                ExpoWhatsappService._send(
                    db,
                    to_number=session.visitor_phone,
                    body=str(vcard.get("caption") or "📇 Save our contact to your phone"),
                    org_id=session.org_id,
                    from_number=from_number,
                    document_link=vurl,
                    document_filename=str(vcard.get("filename") or "contact.vcf")[:240],
                )

        followup = str(result.get("thank_you_followup") or "").strip()
        prompt = followup or str(result.get("prompt") or "").strip()
        if prompt:
            ExpoWhatsappService._send(
                db,
                to_number=session.visitor_phone,
                body=prompt,
                org_id=session.org_id,
                from_number=from_number,
            )

        if result.get("hot_notify_pending"):
            logger.info("expo_wa_hot_lead_notify_pending session=%s", session.id)

    @staticmethod
    def _asset_caption(asset: dict[str, Any]) -> str:
        purpose = str(asset.get("purpose") or "").strip().lower()
        kind = {
            "catalogue": "Catalogue",
            "price_list": "Price list",
            "product_sheet": "Product sheet",
            "product": "File",
        }.get(purpose, "File")
        product = str(asset.get("product_name") or "").strip()
        title = str(asset.get("title") or "our info pack").strip()
        if product:
            label = f"{product} — {kind}"
        else:
            label = f"{kind}: {title}" if title else kind
        desc = str(asset.get("short_description") or "").strip()
        return f"📎 {label}" + (f"\n{desc}" if desc else "")

    @staticmethod
    def _send_asset(
        db: Session,
        *,
        to_number: str,
        asset: dict[str, Any],
        booth_token: str,
        lead_id: str | None,
        org_id: str | None,
        from_number: str | None = None,
    ) -> None:
        title = str(asset.get("title") or "our info pack").strip()
        # Clean public file URL for WhatsApp document fetch (no ?lead_id=).
        file_url = asset_public_url(asset, booth_token, lead_id=None)
        caption = ExpoWhatsappService._asset_caption(asset)
        if _asset_supports_document_send(asset) and file_url.startswith("http"):
            doc_url = _wa_document_url(file_url)
            ok = ExpoWhatsappService._send(
                db,
                to_number=to_number,
                body=caption,
                org_id=org_id,
                from_number=from_number,
                document_link=doc_url,
                document_filename=_asset_document_filename(asset),
            )
            if ok:
                return
            logger.warning(
                "expo_wa_document_send_failed to=%s asset=%s — not pasting link",
                to_number,
                asset.get("id"),
            )
            ExpoWhatsappService._send(
                db,
                to_number=to_number,
                body=(
                    f"📄 {title} — we're attaching the file; if it doesn't appear in chat, "
                    "check your email or ask our stand team."
                ),
                org_id=org_id,
                from_number=from_number,
            )
            return
        # External URL-only assets (no uploaded file) — link is the only option.
        link_body = deliver_asset_link_message(asset, booth_token, lead_id=lead_id)
        ExpoWhatsappService._send(
            db,
            to_number=to_number,
            body=link_body,
            org_id=org_id,
            from_number=from_number,
        )

    @staticmethod
    def _send(
        db: Session,
        *,
        to_number: str,
        body: str,
        org_id: str | None,
        from_number: str | None = None,
        document_link: str | None = None,
        document_filename: str | None = None,
    ) -> bool:
        """Send Expo Q&A / offer copy as plain WhatsApp session text (never a Meta HSM template)."""
        clean = str(body or "").strip()
        if not clean and not document_link:
            return False
        # QR opens the Customer Feedback WhatsApp line — prefer that route so the reply
        # lands in the same chat. Then expo, then platform default.
        # Intentionally omit template_name / template_id so providers send type=text only.
        for code in ("customer_feedback", "expo", None):
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
                document_link=document_link,
                document_filename=document_filename,
            )
            if result.ok:
                logger.info(
                    "expo_wa_session_text_sent to=%s service_code=%s from_line=%s org_id=%s document=%s",
                    to_number,
                    code,
                    from_number,
                    org_id,
                    bool(document_link),
                )
                return True
            logger.warning(
                "expo_wa_send_failed to=%s service_code=%s status=%s detail=%s org_id=%s from_line=%s",
                to_number,
                code,
                result.status,
                result.detail,
                org_id,
                from_number,
            )
        return False
