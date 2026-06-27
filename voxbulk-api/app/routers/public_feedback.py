"""Public web survey API for QR feedback (no auth)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.customer_feedback.web_survey_service import FeedbackWebSurveyService

router = APIRouter(prefix="/public/feedback", tags=["public-feedback"])


@router.get("/survey/{token}")
def get_survey(token: str, db: Session = Depends(get_db)):
    try:
        return {"ok": True, **FeedbackWebSurveyService.survey_payload(db, token)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
    try:
        return {
            "ok": True,
            **FeedbackWebSurveyService.submit_answer(
                db,
                session_id=session_id,
                answer=answer,
                answer_source=str(payload.get("answer_source") or "text"),
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
