"""Public web survey API for QR feedback (no auth)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.customer_feedback.web_survey_service import FeedbackWebSurveyService

router = APIRouter(prefix="/public/feedback", tags=["public-feedback"])

# Cap browser uploads defensively (service also enforces the configured max).
_MAX_VOICE_BYTES = 25 * 1024 * 1024


@router.get("/survey/{token}")
def get_survey(token: str, db: Session = Depends(get_db)):
    try:
        return {"ok": True, **FeedbackWebSurveyService.survey_payload(db, token)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/survey/{token}/logo")
def get_survey_logo(token: str, db: Session = Depends(get_db)):
    try:
        path, media_type = FeedbackWebSurveyService.survey_logo(db, token)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type=media_type)


@router.post("/survey/{token}/sessions")
def start_web_session(token: str, db: Session = Depends(get_db)):
    try:
        return {"ok": True, **FeedbackWebSurveyService.start_session(db, token)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/survey/sessions/{session_id}/answer")
def submit_web_answer(session_id: str, payload: dict, db: Session = Depends(get_db)):
    answer = str(payload.get("answer") or "").strip()
    if not answer:
        raise HTTPException(status_code=400, detail="answer required")
    reason = payload.get("reason")
    try:
        return {
            "ok": True,
            **FeedbackWebSurveyService.submit_answer(
                db,
                session_id=session_id,
                answer=answer,
                answer_source=str(payload.get("answer_source") or "text"),
                reason=(str(reason).strip() if reason else None),
                reason_source=str(payload.get("reason_source") or "text"),
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/survey/sessions/{session_id}/voice")
async def submit_web_voice(
    session_id: str,
    file: UploadFile = File(...),
    mode: str = Form("answer"),
    db: Session = Depends(get_db),
):
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio upload")
    if len(audio_bytes) > _MAX_VOICE_BYTES:
        raise HTTPException(status_code=413, detail="Voice note too large")
    try:
        return {
            "ok": True,
            **FeedbackWebSurveyService.submit_voice(
                db,
                session_id=session_id,
                audio_bytes=audio_bytes,
                filename=file.filename or "voice.webm",
                content_type=file.content_type or "audio/webm",
                mode=("reason" if str(mode).strip().lower() == "reason" else "answer"),
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
