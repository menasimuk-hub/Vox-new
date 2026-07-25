"""Public API — VoxBulk Expo web fallback (no auth). QR → booth info, web lead capture flow."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.expo import ExpoBoothAsset, ExpoSession
from app.services.expo.asset_storage_service import resolve_storage_abs_path
from app.services.expo.booth_service import BOOTH_CLOSED_MESSAGE, ExpoBoothService, booth_is_expired
from app.services.expo.question_bank import parse_contact_capture, web_ui_for_question_key
from app.services.expo.session_flow_service import THANK_YOU_TEXT, ExpoSessionFlowService

router = APIRouter(prefix="/public/expo", tags=["public-expo"])


def _session_for_booth(db: Session, *, booth_id: str, session_id: str) -> ExpoSession:
    session = db.execute(
        select(ExpoSession).where(ExpoSession.id == session_id, ExpoSession.booth_id == booth_id)
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _advance_payload(result: dict) -> dict:
    return {
        "ok": True,
        "done": result.get("done", False),
        "awaiting_pick": result.get("awaiting_pick", False),
        "question": result.get("prompt"),
        "candidates": result.get("candidates"),
        "assets": result.get("assets"),
        "contact_via": result.get("contact_via"),
        "card_fields": result.get("card_fields"),
    }


@router.get("/{token}/logo")
def get_booth_logo(token: str, db: Session = Depends(get_db)):
    from app.models.organisation import Organisation
    from app.services.org_logo_storage_service import media_type_for_key, resolve_logo_path

    booth = ExpoBoothService.find_by_token(db, token)
    if booth is None:
        raise HTTPException(status_code=404, detail="Booth not found")
    org = db.get(Organisation, booth.org_id)
    storage_key = getattr(org, "logo_storage_key", None) if org else None
    if not storage_key:
        raise HTTPException(status_code=404, detail="Logo not found")
    path = resolve_logo_path(str(storage_key))
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Logo not found")
    return FileResponse(path, media_type=media_type_for_key(str(storage_key)))


@router.get("/{token}")
def get_booth_public(token: str, db: Session = Depends(get_db)):
    from urllib.parse import quote
    import re

    from app.models.expo import ExpoExhibition
    from app.models.organisation import Organisation
    from app.services.customer_feedback.feedback_wa_phone import resolve_feedback_wa_phone_for_qr
    from app.services.expo.booth_service import build_trigger_text

    booth = ExpoBoothService.find_by_token(db, token)
    if booth is None:
        raise HTTPException(status_code=404, detail="Booth not found")
    expired = booth_is_expired(booth)
    steps = ExpoSessionFlowService.steps_for_booth(booth)
    exhibition = db.get(ExpoExhibition, booth.exhibition_id)
    event_name = exhibition.name if exhibition else "Exhibition"
    org = db.get(Organisation, booth.org_id)
    country_code = str(getattr(org, "country_code", None) or "gb")
    phone = resolve_feedback_wa_phone_for_qr(db, country_code, org_id=booth.org_id)
    trigger = build_trigger_text(
        company=booth.company_display_name,
        booth=booth.booth_code or booth.name,
        event=event_name,
        token=booth.qr_token,
    )
    digits = re.sub(r"\D+", "", str(phone or ""))
    wa_url = f"https://wa.me/{digits}?text={quote(trigger)}" if digits else ""
    urls = ExpoBoothService.booth_public_urls(booth, event_name=event_name)
    has_logo = bool(org and getattr(org, "logo_storage_key", None))
    contact_capture = parse_contact_capture(booth.question_config_json)
    questions = []
    for step in steps:
        key = str(step.get("key") or "")
        if not key:
            continue
        ui = web_ui_for_question_key(key)
        questions.append(
            {
                "key": key,
                "prompt": str(step.get("prompt_web") or step.get("prompt") or ""),
                "label": str(step.get("label") or key),
                "input": ui["input"],
                "options": ui["options"],
                "allow_voice": bool(ui.get("allow_voice")),
            }
        )
    return {
        "ok": True,
        "token": booth.qr_token,
        "wa_url": wa_url,
        "whatsapp_url": wa_url,
        "web_url": urls["web_url"],
        "theme_id": "survey-temp",
        "company_name": booth.company_display_name,
        "logo_url": f"/public/expo/{booth.qr_token}/logo" if has_logo else None,
        "contact_capture": contact_capture,
        "questions": questions,
        "booth": {
            "name": booth.name,
            "company_display_name": booth.company_display_name,
            "exhibition_name": event_name,
            "status": "expired" if expired else booth.status,
            "is_expired": expired,
            "expires_at": booth.expires_at.isoformat() if booth.expires_at else None,
            "question_count": len(steps),
            "closed_message": BOOTH_CLOSED_MESSAGE if expired else None,
            "contact_capture": contact_capture,
        },
    }


@router.post("/{token}/start")
def start_web_session(token: str, payload: dict, db: Session = Depends(get_db)):
    booth = ExpoBoothService.find_by_token(db, token)
    if booth is None:
        raise HTTPException(status_code=404, detail="Booth not found")
    if booth_is_expired(booth):
        raise HTTPException(status_code=400, detail=BOOTH_CLOSED_MESSAGE)
    if str(booth.status or "").lower() != "active":
        raise HTTPException(status_code=400, detail="This booth is not currently accepting responses.")

    mobile = str(payload.get("mobile") or "").strip()
    email = str(payload.get("email") or "").strip()
    name = str(payload.get("name") or "").strip() or None
    company = str(payload.get("company") or "").strip() or None
    # Real card OCR is POST /sessions/{id}/card after start — start needs phone+email or placeholders for card-first.
    defer_contact = bool(payload.get("defer_contact") or payload.get("card_first"))
    if defer_contact:
        mobile = mobile or f"web-pending-{token[:8]}"
        email = email or "pending@expo.local"
    elif not mobile or not email:
        raise HTTPException(
            status_code=400,
            detail="mobile and email are required (or start with card_first and upload a business card)",
        )

    result = ExpoSessionFlowService.start_session(
        db,
        booth=booth,
        channel="web",
        visitor_phone=mobile,
        visitor_email=email,
        name=name,
    )
    session_id = result["session_id"]

    # Typed contact on the landing form → advance name + company (+ mobile already on session)
    if not defer_contact and name and company:
        session = db.get(ExpoSession, session_id)
        if session is not None:
            ExpoSessionFlowService.advance(db, session=session, answer=name, answer_source="text")
            session = db.get(ExpoSession, session_id)
            if session is not None and session.status == "active":
                result = ExpoSessionFlowService.advance(
                    db, session=session, answer=company, answer_source="text"
                )

    out = _advance_payload(result)
    out["session_id"] = session_id
    return out


@router.post("/{token}/sessions/{session_id}/card")
async def upload_business_card(
    token: str,
    session_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    from app.services.expo.business_card_ocr_service import ExpoBusinessCardService

    booth = ExpoBoothService.find_by_token(db, token)
    if booth is None:
        raise HTTPException(status_code=404, detail="Booth not found")
    if booth_is_expired(booth) or str(booth.status or "").lower() != "active":
        raise HTTPException(status_code=400, detail=BOOTH_CLOSED_MESSAGE)
    session = _session_for_booth(db, booth_id=booth.id, session_id=session_id)
    if session.status != "active":
        return {"ok": True, "done": True, "question": THANK_YOU_TEXT}

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty image upload")
    ctype = str(file.content_type or "image/jpeg")
    fields, card_path = ExpoBusinessCardService.save_from_bytes(
        db,
        org_id=booth.org_id,
        booth_id=booth.id,
        image_bytes=raw,
        content_type=ctype,
    )
    # Prefer OCR phone/email over web pending placeholders
    if fields.get("phone"):
        session.visitor_phone = str(fields["phone"])[:32]
    if fields.get("email"):
        session.visitor_email = str(fields["email"])[:255]
    db.add(session)
    db.commit()

    result = ExpoSessionFlowService.advance(
        db,
        session=session,
        answer="[business card image]",
        answer_source="image",
        contact_fields=fields,
        business_card_path=card_path,
    )
    out = _advance_payload(result)
    out["session_id"] = session_id
    out["card_fields"] = fields
    return out


@router.post("/{token}/sessions/{session_id}/voice")
async def upload_voice_answer(
    token: str,
    session_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    from app.services.expo.voice_note_service import process_web_voice_bytes

    booth = ExpoBoothService.find_by_token(db, token)
    if booth is None:
        raise HTTPException(status_code=404, detail="Booth not found")
    session = _session_for_booth(db, booth_id=booth.id, session_id=session_id)
    if session.status != "active":
        return {"ok": True, "done": True, "question": THANK_YOU_TEXT}

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty audio upload")
    voice = process_web_voice_bytes(
        db,
        session=session,
        audio_bytes=raw,
        filename=file.filename or "voice.webm",
        content_type=str(file.content_type or "audio/webm"),
    )
    if not voice.get("ok"):
        raise HTTPException(
            status_code=400,
            detail="Sorry — I couldn't hear that clearly. Please type your answer, or record again.",
        )

    session = db.get(ExpoSession, session_id) or session
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
    out = _advance_payload(result)
    out["session_id"] = session_id
    out["original_text"] = voice.get("original_text")
    out["answer_text_en"] = voice.get("answer_text_en")
    return out


@router.post("/{token}/answer")
def answer_web_session(token: str, payload: dict, db: Session = Depends(get_db)):
    booth = ExpoBoothService.find_by_token(db, token)
    if booth is None:
        raise HTTPException(status_code=404, detail="Booth not found")

    session_id = str(payload.get("session_id") or "").strip()
    answer = str(payload.get("answer") or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    if not answer:
        raise HTTPException(status_code=400, detail="answer required")

    session = _session_for_booth(db, booth_id=booth.id, session_id=session_id)
    if session.status != "active":
        return {"ok": True, "done": True, "question": THANK_YOU_TEXT}

    result = ExpoSessionFlowService.advance(db, session=session, answer=answer, answer_source="text")
    out = _advance_payload(result)
    out["session_id"] = session_id
    return out


@router.get("/assets/{token}/{asset_id}")
def get_booth_asset(token: str, asset_id: str, db: Session = Depends(get_db)):
    booth = ExpoBoothService.find_by_token(db, token)
    if booth is None:
        raise HTTPException(status_code=404, detail="Booth not found")
    asset = db.execute(
        select(ExpoBoothAsset).where(ExpoBoothAsset.id == asset_id, ExpoBoothAsset.booth_id == booth.id)
    ).scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset.external_url:
        return RedirectResponse(asset.external_url)
    abs_path = resolve_storage_abs_path(asset.storage_path)
    if abs_path is not None:
        filename = abs_path.name
        suffix = abs_path.suffix.lower()
        media = None
        if suffix == ".pdf":
            media = "application/pdf"
        elif suffix in {".xls"}:
            media = "application/vnd.ms-excel"
        elif suffix in {".xlsx"}:
            media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif suffix == ".csv":
            media = "text/csv"
        return FileResponse(abs_path, filename=filename, media_type=media)
    raise HTTPException(status_code=404, detail="Asset file not available yet")
