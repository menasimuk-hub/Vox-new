"""Public API — VoxBulk Expo web fallback (no auth). QR → booth info, web lead capture flow."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.expo import ExpoBoothAsset, ExpoLead, ExpoLibraryAsset, ExpoSession
from app.services.expo.asset_storage_service import resolve_storage_abs_path
from app.services.expo.booth_service import (
    BOOTH_CLOSED_MESSAGE,
    ExpoBoothService,
    booth_access_block_reason,
    booth_is_before_start,
    booth_is_expired,
    booth_is_live,
    booth_is_paid,
    booth_preview_remaining,
)
from app.services.expo.offer_delivery_service import asset_public_url, load_booth_assets, mark_lead_asset_opened
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


def _advance_payload(
    result: dict,
    *,
    session: ExpoSession | None = None,
    booth=None,
    token: str | None = None,
    db: Session | None = None,
) -> dict:
    lead_id: str | None = None
    if db is not None and session is not None:
        lead_row = db.execute(select(ExpoLead).where(ExpoLead.session_id == session.id)).scalar_one_or_none()
        lead_id = str(lead_row.id) if lead_row else None

    def _public_asset(a: dict) -> dict:
        url = str(a.get("url") or "").strip() or (
            asset_public_url(a, token, lead_id=lead_id) if token else ""
        )
        return {
            "id": a.get("id"),
            "title": a.get("title"),
            "short_description": a.get("short_description"),
            "kind": a.get("kind"),
            "purpose": a.get("purpose"),
            "url": url,
        }

    assets = result.get("assets")
    asset_options = result.get("asset_options")

    public_assets = None
    if isinstance(assets, list) and assets and token:
        public_assets = [_public_asset(a) for a in assets if isinstance(a, dict)]
    elif isinstance(asset_options, list) and asset_options and token and not assets:
        # Consent "ask" step carries no deliverable assets yet — web can still show
        # downloadable previews for the offered catalogue/price-list files.
        public_assets = [_public_asset(a) for a in asset_options if isinstance(a, dict)]
    elif isinstance(assets, list) and token:
        public_assets = []

    public_asset_options = None
    if isinstance(asset_options, list) and token:
        public_asset_options = [_public_asset(a) for a in asset_options if isinstance(a, dict)]

    out = {
        "ok": True,
        "done": result.get("done", False),
        "awaiting_pick": result.get("awaiting_pick", False),
        "question": result.get("prompt"),
        "question_key": result.get("question_key"),
        "contact_substep": result.get("contact_substep"),
        "input": result.get("input"),
        "options": result.get("options") or [],
        "allow_voice": bool(result.get("allow_voice")),
        "candidates": result.get("candidates"),
        "assets": public_assets if public_assets is not None else assets,
        "asset_options": public_asset_options if public_asset_options is not None else asset_options,
        "thank_you_followup": result.get("thank_you_followup"),
        "company_card": result.get("company_card"),
        "representatives": result.get("representatives"),
        "company_website": result.get("company_website"),
        "company_logo_url": (
            f"/public/expo/{token}/logo" if token and result.get("company_logo_url") else result.get("company_logo_url")
        ),
        "pre_thank_you_messages": result.get("pre_thank_you_messages"),
        "vcard_url": f"/public/expo/{token}/vcard" if token else result.get("vcard_url_hint"),
        "contact_via": result.get("contact_via"),
        "card_fields": result.get("card_fields"),
        "summary": result.get("summary"),
        "at_start": bool(result.get("at_start")),
        "step_index": result.get("step_index"),
        "step_total": result.get("step_total"),
    }
    if session is not None and (out["step_index"] is None or out["step_total"] is None):
        meta = ExpoSessionFlowService._attach_progress({}, session=session, booth=booth)
        out["step_index"] = out["step_index"] or meta.get("step_index")
        out["step_total"] = out["step_total"] or meta.get("step_total")
    return out


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


@router.get("/{token}/vcard")
def get_booth_vcard(token: str, db: Session = Depends(get_db)):
    """Download exhibitor representative contacts as a .vcf for Save to phone."""
    booth = ExpoBoothService.find_by_token(db, token)
    if booth is None:
        raise HTTPException(status_code=404, detail="Booth not found")
    body = ExpoBoothService.booth_vcard(db, booth)
    filename = f"{(booth.company_display_name or booth.name or 'contact').replace(' ', '-')[:40]}.vcf"
    return Response(
        content=body,
        media_type="text/vcard",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

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
    archived = str(booth.status or "").lower() == "archived"
    before_start = booth_is_before_start(booth)
    preview_remaining = booth_preview_remaining(booth)
    paid = booth_is_paid(booth)
    live = booth_is_live(booth)
    closed_message = booth_access_block_reason(booth)
    if expired or archived:
        closed_message = BOOTH_CLOSED_MESSAGE
    public_status = (
        "archived"
        if archived
        else (
            "expired"
            if expired
            else (
                "unpaid"
                if not paid
                else ("preview" if before_start else ("live" if live else str(booth.status or "paused")))
            )
        )
    )
    steps = ExpoSessionFlowService.steps_for_booth(booth)
    exhibition = db.get(ExpoExhibition, booth.exhibition_id)
    event_name = exhibition.name if exhibition else "Exhibition"
    starts_on = None
    ends_on = None
    if exhibition and exhibition.starts_on:
        starts_on = exhibition.starts_on.isoformat()
    elif booth.activated_at:
        starts_on = booth.activated_at.isoformat()
    if exhibition and exhibition.ends_on:
        ends_on = exhibition.ends_on.isoformat()
    elif booth.expires_at:
        ends_on = booth.expires_at.isoformat()
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
        prompt = str(step.get("prompt_web") or step.get("prompt") or "")
        if key == "consent_info":
            prompt = "Would you like our catalogue or price list?"
        questions.append(
            {
                "key": key,
                "prompt": prompt,
                "label": str(step.get("label") or key),
                "input": ui["input"],
                "options": ui["options"],
                "allow_voice": bool(ui.get("allow_voice")),
            }
        )
    booth_assets = load_booth_assets(db, booth.id)
    public_assets = [
        {
            "id": a.get("id"),
            "title": a.get("title"),
            "short_description": a.get("short_description"),
            "kind": a.get("kind"),
            "url": asset_public_url(a, booth.qr_token),
        }
        for a in booth_assets
    ]
    return {
        "ok": True,
        "token": booth.qr_token,
        "wa_url": wa_url,
        "whatsapp_url": wa_url,
        "web_url": urls["web_url"],
        "theme_id": "expo",
        "company_name": booth.company_display_name,
        "logo_url": f"/public/expo/{booth.qr_token}/logo" if has_logo else None,
        "logo_tone": (getattr(org, "logo_tone", None) or None) if org and has_logo else None,
        "contact_capture": contact_capture,
        "questions": questions,
        "assets": public_assets,
        "step_total": len(steps),
        "booth": {
            "name": booth.name,
            "company_display_name": booth.company_display_name,
            "exhibition_id": booth.exhibition_id,
            "exhibition_name": event_name,
            "status": public_status,
            "is_expired": expired or archived,
            "is_archived": archived,
            "is_before_start": before_start,
            "is_paid": paid,
            "is_live": live,
            "is_preview_draft": bool(getattr(booth, "is_preview_draft", False)),
            "payment_status": str(getattr(booth, "payment_status", None) or "unpaid"),
            "preview_tests_remaining": preview_remaining,
            "activated_at": booth.activated_at.isoformat() if booth.activated_at else None,
            "expires_at": booth.expires_at.isoformat() if booth.expires_at else None,
            "starts_on": starts_on,
            "ends_on": ends_on,
            "question_count": len(steps),
            "closed_message": closed_message,
            "contact_capture": contact_capture,
        },
    }


@router.post("/{token}/start")
def start_web_session(token: str, payload: dict, db: Session = Depends(get_db)):
    booth = ExpoBoothService.find_by_token(db, token)
    if booth is None:
        raise HTTPException(status_code=404, detail="Booth not found")
    if booth_is_expired(booth) and not bool(getattr(booth, "is_preview_draft", False)):
        raise HTTPException(status_code=400, detail=BOOTH_CLOSED_MESSAGE)
    block = booth_access_block_reason(booth)
    if block:
        raise HTTPException(status_code=400, detail=block)
    if str(booth.status or "").lower() != "active":
        raise HTTPException(status_code=400, detail="This booth is not currently accepting responses.")

    mobile = str(payload.get("mobile") or "").strip()
    email = str(payload.get("email") or "").strip()
    name = str(payload.get("name") or "").strip() or None
    company = str(payload.get("company") or "").strip() or None
    visitor_token = str(payload.get("visitor_token") or "").strip() or None
    is_preview = bool(payload.get("preview") or payload.get("is_preview")) or bool(
        getattr(booth, "is_preview_draft", False)
    )
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

    try:
        result = ExpoSessionFlowService.start_session(
            db,
            booth=booth,
            channel="web",
            visitor_phone=mobile,
            visitor_email=email,
            name=name,
            company=company,
            visitor_token=visitor_token,
            is_preview=is_preview,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
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

    out = _advance_payload(result, session=db.get(ExpoSession, session_id), booth=booth, token=token, db=db)
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
    block = booth_access_block_reason(booth)
    if block:
        raise HTTPException(status_code=400, detail=block)
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
    # Prefer OCR phone/email/name over web pending placeholders (session + lead)
    lead = db.execute(
        select(ExpoLead).where(ExpoLead.session_id == session.id).limit(1)
    ).scalar_one_or_none()
    if fields.get("phone"):
        session.visitor_phone = str(fields["phone"])[:32]
        if lead is not None:
            lead.visitor_phone = str(fields["phone"])[:32]
    if fields.get("email"):
        session.visitor_email = str(fields["email"])[:255]
        if lead is not None:
            lead.visitor_email = str(fields["email"])[:255]
    if fields.get("name") and lead is not None:
        lead.name = str(fields["name"])[:255]
    if fields.get("company") and lead is not None:
        lead.company = str(fields["company"])[:255]
    if card_path and lead is not None:
        lead.business_card_path = str(card_path)[:2000]
    if lead is not None:
        lead.updated_at = datetime.utcnow()
        db.add(lead)
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
    session = db.get(ExpoSession, session_id) or session
    out = _advance_payload(result, session=session, booth=booth, token=token, db=db)
    out["session_id"] = session_id
    out["card_fields"] = fields or result.get("card_fields")
    return out


@router.post("/{token}/sessions/{session_id}/contact")
def confirm_web_contact(token: str, session_id: str, payload: dict, db: Session = Depends(get_db)):
    """Editable confirm after business-card OCR (rejects pending@expo.local placeholders)."""
    booth = ExpoBoothService.find_by_token(db, token)
    if booth is None:
        raise HTTPException(status_code=404, detail="Booth not found")
    session = _session_for_booth(db, booth_id=booth.id, session_id=session_id)
    if session.status != "active":
        return {"ok": True, "done": True, "question": THANK_YOU_TEXT}

    result = ExpoSessionFlowService.confirm_contact(
        db,
        session=session,
        name=str(payload.get("name") or "").strip() or None,
        company=str(payload.get("company") or "").strip() or None,
        mobile=str(payload.get("mobile") or payload.get("phone") or "").strip() or None,
        email=str(payload.get("email") or "").strip() or None,
    )
    session = db.get(ExpoSession, session_id) or session
    out = _advance_payload(result, session=session, booth=booth, token=token, db=db)
    out["session_id"] = session_id
    if result.get("card_fields"):
        out["card_fields"] = result["card_fields"]
    if not result.get("done") and result.get("contact_substep") == "confirm" and str(result.get("prompt") or "").startswith("Please"):
        out["error"] = str(result.get("prompt") or "")
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
    session = db.get(ExpoSession, session_id) or session
    out = _advance_payload(result, session=session, booth=booth, token=token, db=db)
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
    session = db.get(ExpoSession, session_id) or session
    out = _advance_payload(result, session=session, booth=booth, token=token, db=db)
    out["session_id"] = session_id
    return out


@router.get("/{token}/sessions/{session_id}")
def get_web_session_state(token: str, session_id: str, db: Session = Depends(get_db)):
    """Current step without consuming an answer — lets a refreshed tab resume via localStorage."""
    booth = ExpoBoothService.find_by_token(db, token)
    if booth is None:
        raise HTTPException(status_code=404, detail="Booth not found")
    session = _session_for_booth(db, booth_id=booth.id, session_id=session_id)
    result = ExpoSessionFlowService.current_prompt(db, session=session, booth=booth)
    session = db.get(ExpoSession, session_id) or session
    out = _advance_payload(result, session=session, booth=booth, token=token, db=db)
    out["session_id"] = session_id
    return out


@router.post("/{token}/sessions/{session_id}/back")
def go_back_web_session(token: str, session_id: str, db: Session = Depends(get_db)):
    """Rewind one step so web Back matches the previous slide."""
    booth = ExpoBoothService.find_by_token(db, token)
    if booth is None:
        raise HTTPException(status_code=404, detail="Booth not found")
    session = _session_for_booth(db, booth_id=booth.id, session_id=session_id)
    result = ExpoSessionFlowService.go_back(db, session=session)
    session = db.get(ExpoSession, session_id) or session
    out = _advance_payload(result, session=session, booth=booth, token=token, db=db)
    out["session_id"] = session_id
    return out


@router.post("/{token}/sessions/{session_id}/stop")
def stop_web_session(token: str, session_id: str, db: Session = Depends(get_db)):
    """Visitor left mid-flow — keep collected answers, mark done, return summary."""
    booth = ExpoBoothService.find_by_token(db, token)
    if booth is None:
        raise HTTPException(status_code=404, detail="Booth not found")
    session = _session_for_booth(db, booth_id=booth.id, session_id=session_id)
    result = ExpoSessionFlowService.stop(db, session=session)
    session = db.get(ExpoSession, session_id) or session
    out = _advance_payload(result, session=session, booth=booth, token=token, db=db)
    out["session_id"] = session_id
    return out


@router.get("/assets/{token}/{asset_id}")
def get_booth_asset(
    token: str,
    asset_id: str,
    lead_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    booth = ExpoBoothService.find_by_token(db, token)
    if booth is None:
        raise HTTPException(status_code=404, detail="Booth not found")
    asset = db.execute(
        select(ExpoBoothAsset).where(ExpoBoothAsset.id == asset_id, ExpoBoothAsset.booth_id == booth.id)
    ).scalar_one_or_none()
    library_asset = None
    if asset is None:
        # Add catalogues library files are org-scoped and offered on every booth.
        library_asset = db.execute(
            select(ExpoLibraryAsset).where(
                ExpoLibraryAsset.id == asset_id,
                ExpoLibraryAsset.org_id == booth.org_id,
            )
        ).scalar_one_or_none()
    if asset is None and library_asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")

    track_asset: ExpoBoothAsset | dict = asset or {
        "id": library_asset.id,
        "asset_key": f"lib-{library_asset.id}",
        "purpose": library_asset.purpose,
        "title": library_asset.title,
    }

    # Open / download tracking (first open only).
    if lead_id:
        lead = db.execute(
            select(ExpoLead).where(
                ExpoLead.id == str(lead_id).strip(),
                ExpoLead.booth_id == booth.id,
                ExpoLead.org_id == booth.org_id,
            )
        ).scalar_one_or_none()
        if lead is not None:
            try:
                if mark_lead_asset_opened(db, lead=lead, asset=track_asset):
                    db.commit()
            except Exception:
                db.rollback()

    external = (asset.external_url if asset is not None else library_asset.external_url) if (
        asset is not None or library_asset is not None
    ) else None
    if external:
        return RedirectResponse(external)
    storage = asset.storage_path if asset is not None else library_asset.storage_path
    abs_path = resolve_storage_abs_path(storage)
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
