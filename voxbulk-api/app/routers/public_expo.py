"""Public API — VoxBulk Expo web fallback (no auth). QR → booth info, web lead capture flow."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.expo import ExpoBoothAsset, ExpoSession
from app.services.expo.asset_storage_service import resolve_storage_abs_path
from app.services.expo.booth_service import ExpoBoothService
from app.services.expo.session_flow_service import THANK_YOU_TEXT, ExpoSessionFlowService

router = APIRouter(prefix="/public/expo", tags=["public-expo"])


@router.get("/{token}")
def get_booth_public(token: str, db: Session = Depends(get_db)):
    booth = ExpoBoothService.find_by_token(db, token)
    if booth is None:
        raise HTTPException(status_code=404, detail="Booth not found")
    steps = ExpoSessionFlowService.steps_for_booth(booth)
    return {
        "ok": True,
        "booth": {
            "name": booth.name,
            "company_display_name": booth.company_display_name,
            "status": booth.status,
            "question_count": len(steps),
        },
    }


@router.post("/{token}/start")
def start_web_session(token: str, payload: dict, db: Session = Depends(get_db)):
    booth = ExpoBoothService.find_by_token(db, token)
    if booth is None:
        raise HTTPException(status_code=404, detail="Booth not found")
    if str(booth.status or "").lower() != "active":
        raise HTTPException(status_code=400, detail="This booth is not currently accepting responses.")

    mobile = str(payload.get("mobile") or "").strip()
    email = str(payload.get("email") or "").strip()
    name = str(payload.get("name") or "").strip() or None
    company = str(payload.get("company") or "").strip() or None
    card_uploaded = bool(payload.get("business_card") or payload.get("has_business_card"))
    # Card photo skips name/company/mobile; otherwise mobile + email required.
    if card_uploaded:
        mobile = mobile or f"web-card-{token[:8]}"
        email = email or "card@expo.local"
    elif not mobile or not email:
        raise HTTPException(status_code=400, detail="mobile and email are required (or upload a business card)")

    result = ExpoSessionFlowService.start_session(
        db,
        booth=booth,
        channel="web",
        visitor_phone=mobile,
        visitor_email=email,
        name=name,
    )
    session_id = result["session_id"]
    # If visitor already provided card or typed contact on the landing form, advance contact.
    if card_uploaded:
        session = db.get(ExpoSession, session_id)
        if session is not None:
            result = ExpoSessionFlowService.advance(
                db, session=session, answer="[business card image]", answer_source="image"
            )
    elif name and company:
        session = db.get(ExpoSession, session_id)
        if session is not None:
            ExpoSessionFlowService.advance(db, session=session, answer=name, answer_source="text")
            session = db.get(ExpoSession, session_id)
            if session is not None and session.status == "active":
                result = ExpoSessionFlowService.advance(db, session=session, answer=company, answer_source="text")

    return {
        "ok": True,
        "session_id": session_id,
        "done": result.get("done", False),
        "question": result.get("prompt"),
        "awaiting_pick": result.get("awaiting_pick", False),
        "candidates": result.get("candidates"),
        "assets": result.get("assets"),
    }


@router.post("/{token}/answer")
def answer_web_session(token: str, payload: dict, db: Session = Depends(get_db)):
    booth = ExpoBoothService.find_by_token(db, token)
    if booth is None:
        raise HTTPException(status_code=404, detail="Booth not found")

    session_id = str(payload.get("session_id") or "").strip()
    answer = str(payload.get("answer") or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    session = db.execute(
        select(ExpoSession).where(ExpoSession.id == session_id, ExpoSession.booth_id == booth.id)
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != "active":
        return {"ok": True, "done": True, "question": THANK_YOU_TEXT}

    result = ExpoSessionFlowService.advance(db, session=session, answer=answer, answer_source="text")
    return {
        "ok": True,
        "done": result.get("done", False),
        "awaiting_pick": result.get("awaiting_pick", False),
        "question": result.get("prompt"),
        "candidates": result.get("candidates"),
        "assets": result.get("assets"),
    }


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
