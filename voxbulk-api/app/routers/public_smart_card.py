"""Public Smart Card QR landing + web session."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.smart_card import SmartCardRepresentative, SmartCardSession
from app.services.smart_card.company_service import SmartCardCompanyService, SmartCardEntitlementService
from app.services.smart_card.session_flow_service import SmartCardSessionError, SmartCardSessionFlowService

router = APIRouter(prefix="/public/smart-card", tags=["public-smart-card"])


def _get_rep(db: Session, token: str) -> SmartCardRepresentative:
    rep = db.execute(
        select(SmartCardRepresentative).where(SmartCardRepresentative.qr_token == token)
    ).scalar_one_or_none()
    if rep is None or str(rep.status or "") != "active":
        raise HTTPException(status_code=404, detail="Smart Card QR not found")
    return rep


@router.get("/{token}")
def get_card(token: str, db: Session = Depends(get_db)):
    rep = _get_rep(db, token)
    company = SmartCardCompanyService.get_or_create(db, rep.org_id)
    mode = SmartCardEntitlementService.access_mode(db, rep.org_id)
    renew_url = "https://dashboard.voxbulk.com/account/smart-card/packages"

    if mode == "expired":
        return {
            "ok": True,
            "status": "expired",
            "message": (
                "We're sorry — this Smart Card QR account has expired. "
                "Please ask the company to renew their package."
            ),
            "renew_url": renew_url,
            "representative": {"name": rep.name},
            "company": {"name": company.name},
        }

    if mode == "preview_exhausted":
        return {
            "ok": True,
            "status": "preview_exhausted",
            "message": (
                "Preview tests are used up (15). "
                "This Smart Card QR will go live after the organisation buys or renews a package."
            ),
            "renew_url": renew_url,
            "representative": {"name": rep.name},
            "company": {"name": company.name},
        }

    from app.services.connection.config_resolver import whatsapp_route_whatsapp_from
    from app.services.connection.constants import SERVICE_SMART_CARD, SERVICE_CUSTOMER_FEEDBACK

    wa_phone = (
        whatsapp_route_whatsapp_from(db, org_id=rep.org_id, service_code=SERVICE_SMART_CARD)
        or whatsapp_route_whatsapp_from(db, org_id=rep.org_id, service_code=SERVICE_CUSTOMER_FEEDBACK)
        or ""
    )
    if not wa_phone:
        try:
            from app.services.customer_feedback.feedback_wa_phone import resolve_feedback_wa_phone_for_qr

            wa_phone = resolve_feedback_wa_phone_for_qr(db, "gb", org_id=rep.org_id) or ""
        except Exception:
            wa_phone = ""
    from urllib.parse import quote

    from app.services.smart_card.whatsapp_service import build_smart_card_wa_trigger

    wa_digits = "".join(c for c in wa_phone if c.isdigit())
    trigger = build_smart_card_wa_trigger(rep_name=rep.name, qr_token=rep.qr_token)
    wa_url = f"https://wa.me/{wa_digits}?text={quote(trigger)}" if wa_digits else None
    feedback_wa_url = wa_url

    social = None
    if rep.social_links_json:
        try:
            social = json.loads(rep.social_links_json)
        except Exception:
            social = None

    extra: dict = {}
    if rep.extra_json:
        try:
            parsed_extra = json.loads(rep.extra_json)
            if isinstance(parsed_extra, dict):
                extra = parsed_extra
        except Exception:
            extra = {}

    brand: dict = {}
    if company.brand_defaults_json:
        try:
            parsed_brand = json.loads(company.brand_defaults_json)
            if isinstance(parsed_brand, dict):
                brand = parsed_brand
        except Exception:
            brand = {}

    job_title = (
        str(extra.get("job_title") or extra.get("title") or extra.get("role") or "").strip() or None
    )
    location = (
        str(brand.get("address") or brand.get("location") or extra.get("location") or "").strip() or None
    )
    tagline = (str(company.description or "").strip() or None)

    from app.models.organisation import Organisation

    org = db.get(Organisation, rep.org_id)
    has_logo = bool(org and getattr(org, "logo_storage_key", None))

    return {
        "ok": True,
        "status": mode,
        "preview_tests_remaining": max(0, 15 - int(company.preview_tests_used or 0))
        if mode == "preview"
        else None,
        "representative": {
            "id": rep.id,
            "name": rep.name,
            "email": rep.email,
            "website": rep.website,
            "mobile": rep.mobile,
            "landline": rep.landline,
            "extension": rep.extension,
            "job_title": job_title,
            "social_links": social,
            "photo_url": (
                f"/public/smart-card/{token}/photo" if rep.photo_storage_path else None
            ),
        },
        "company": {
            "name": company.name,
            "website": company.website,
            "description": company.description,
            "tagline": tagline,
            "location": location,
            "logo_url": f"/public/smart-card/{token}/logo" if has_logo else None,
        },
        "qr_token": rep.qr_token,
        "whatsapp_url": wa_url,
        "feedback_whatsapp_url": feedback_wa_url or wa_url,
    }


@router.get("/{token}/logo")
def get_card_logo(token: str, db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse

    from app.models.organisation import Organisation
    from app.services.org_logo_storage_service import media_type_for_key, resolve_logo_path

    rep = _get_rep(db, token)
    org = db.get(Organisation, rep.org_id)
    storage_key = getattr(org, "logo_storage_key", None) if org else None
    if not storage_key:
        raise HTTPException(status_code=404, detail="Logo not found")
    path = resolve_logo_path(str(storage_key))
    if path is None:
        raise HTTPException(status_code=404, detail="Logo not found")
    return FileResponse(path, media_type=media_type_for_key(str(storage_key)))


@router.get("/{token}/photo")
def get_card_photo(token: str, db: Session = Depends(get_db)):
    from pathlib import Path

    from fastapi.responses import FileResponse

    rep = _get_rep(db, token)
    if not rep.photo_storage_path:
        raise HTTPException(status_code=404, detail="Photo not found")
    root = Path(__file__).resolve().parents[2]
    abs_path = (root / str(rep.photo_storage_path)).resolve()
    try:
        abs_path.relative_to((root / "data").resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="Photo not found") from None
    if not abs_path.is_file():
        raise HTTPException(status_code=404, detail="Photo not found")
    suffix = abs_path.suffix.lower()
    media = "image/jpeg"
    if suffix == ".png":
        media = "image/png"
    elif suffix == ".webp":
        media = "image/webp"
    return FileResponse(abs_path, media_type=media)


@router.post("/{token}/start")
def start_session(token: str, payload: dict | None = None, db: Session = Depends(get_db)):
    rep = _get_rep(db, token)
    payload = payload or {}
    try:
        result = SmartCardSessionFlowService.start_session(
            db,
            rep=rep,
            channel="web",
            visitor_phone=(str(payload.get("mobile") or "").strip() or None),
            visitor_email=(str(payload.get("email") or "").strip() or None),
            name=(str(payload.get("name") or "").strip() or None),
            company_name=(str(payload.get("company") or "").strip() or None),
        )
        db.commit()
        return result
    except SmartCardSessionError as e:
        code = str(e)
        if code in {"expired", "preview_exhausted"}:
            raise HTTPException(status_code=403, detail=code) from e
        raise HTTPException(status_code=400, detail=code) from e


@router.post("/{token}/answer")
def answer_session(token: str, payload: dict, db: Session = Depends(get_db)):
    rep = _get_rep(db, token)
    session_id = str((payload or {}).get("session_id") or "").strip()
    session = db.get(SmartCardSession, session_id)
    if session is None or session.representative_id != rep.id:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        result = SmartCardSessionFlowService.advance(
            db,
            session=session,
            answer=str((payload or {}).get("answer") or ""),
            answer_source=str((payload or {}).get("answer_source") or "text"),
        )
        db.commit()
        return result
    except SmartCardSessionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{token}/sessions/{session_id}/back")
def step_back(token: str, session_id: str, db: Session = Depends(get_db)):
    """Rewind one question without losing the scanned business card or typed contact details."""
    rep = _get_rep(db, token)
    session = db.get(SmartCardSession, session_id)
    if session is None or session.representative_id != rep.id:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        result = SmartCardSessionFlowService.go_back(db, session=session)
        db.commit()
        return result
    except SmartCardSessionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{token}/card")
async def upload_card(
    token: str,
    session_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    rep = _get_rep(db, token)
    session = db.get(SmartCardSession, session_id)
    if session is None or session.representative_id != rep.id:
        raise HTTPException(status_code=404, detail="Session not found")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    extracted: dict = {"name": None, "company": None, "email": None, "phone": None}
    card_path: str | None = None
    try:
        from app.services.expo.business_card_ocr_service import ExpoBusinessCardService

        extracted, card_path = ExpoBusinessCardService.save_from_bytes(
            db,
            org_id=str(rep.org_id),
            booth_id=str(rep.id),
            image_bytes=raw,
            content_type=file.content_type or "image/jpeg",
        )
        extracted = extracted or {"name": None, "company": None, "email": None, "phone": None}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OCR unavailable: {e}") from e

    result = SmartCardSessionFlowService.apply_card_ocr(
        db,
        session=session,
        name=(extracted or {}).get("name"),
        company=(extracted or {}).get("company"),
        email=(extracted or {}).get("email"),
        phone=(extracted or {}).get("phone"),
        business_card_path=card_path,
    )
    db.commit()
    return result


@router.post("/{token}/sessions/{session_id}/voice")
async def upload_voice_answer(
    token: str,
    session_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Web voice note — store original audio, STT for answer text, advance session."""
    from app.services.smart_card.voice_note_service import process_web_voice_bytes

    rep = _get_rep(db, token)
    session = db.get(SmartCardSession, session_id)
    if session is None or session.representative_id != rep.id:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != "active":
        return {"ok": True, "done": True, "message": "Thank you"}

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

    session = db.get(SmartCardSession, session_id) or session
    try:
        result = SmartCardSessionFlowService.advance(
            db,
            session=session,
            answer=str(voice.get("answer_text_en") or voice.get("original_text") or ""),
            answer_source="voice",
            original_text=str(voice.get("original_text") or "") or None,
            answer_text_en=str(voice.get("answer_text_en") or "") or None,
            voice_job_id=str(voice.get("job_id") or "") or None,
        )
        db.commit()
    except SmartCardSessionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    result["original_text"] = voice.get("original_text")
    result["answer_text_en"] = voice.get("answer_text_en")
    result["voice_job_id"] = voice.get("job_id")
    return result
