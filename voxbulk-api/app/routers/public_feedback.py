"""Public web survey API for QR feedback (no auth).

Mutating session endpoints require the location QR ``token`` query param so a
leaked session_id alone cannot submit answers (M4).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.customer_feedback.web_survey_service import FeedbackWebSurveyService


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    ip = forwarded or (request.client.host if request.client else None)
    ua = (request.headers.get("user-agent") or "").strip() or None
    return ip, ua

router = APIRouter(prefix="/public/feedback", tags=["public-feedback"])

# Cap browser uploads defensively (service also enforces the configured max).
_MAX_VOICE_BYTES = 25 * 1024 * 1024


@router.get("/survey/{token}")
def get_survey(token: str, db: Session = Depends(get_db)):
    try:
        return {"ok": True, **FeedbackWebSurveyService.survey_payload(db, token)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{token}/qr.png")
def get_feedback_qr_png(
    token: str,
    s: int = Query(default=512, ge=64, le=2048),
    fg: str | None = Query(default=None),
    bg: str | None = Query(default=None),
    t: str | None = Query(default=None),
    m: str | None = Query(default=None),
    c: str | None = Query(default=None),
    a: str | None = Query(default=None),
    f: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    from fastapi.responses import Response
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.models.customer_feedback import FeedbackLocation
    from app.services.qr_style_render import (
        merge_style_query_overrides,
        render_styled_qr_png,
        style_kwargs_from_row,
    )

    clean = str(token or "").strip().lower()
    row = db.execute(select(FeedbackLocation).where(FeedbackLocation.qr_token == clean)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Location not found")
    web_base = get_settings().public_site_base_url.rstrip("/")
    web_url = f"{web_base}/survey/{row.qr_token}"
    overrides = merge_style_query_overrides(
        style_kwargs_from_row(row),
        fg=fg,
        bg=bg,
        t=t,
        m=m,
        c=c,
        a=a,
        f=f,
    )
    png = render_styled_qr_png(web_url, size=int(s), **overrides)
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Content-Disposition": f'inline; filename="feedback-{clean[:40]}.png"',
            "Cache-Control": "public, max-age=300",
        },
    )

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
def submit_web_answer(
    session_id: str,
    payload: dict,
    token: str = Query(..., min_length=6),
    db: Session = Depends(get_db),
):
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
                token=token,
                answer=answer,
                answer_source=str(payload.get("answer_source") or "text"),
                reason=(str(reason).strip() if reason else None),
                reason_source=str(payload.get("reason_source") or "text"),
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/survey/sessions/{session_id}/callback-consent")
def submit_web_callback_consent(
    session_id: str,
    payload: dict,
    request: Request,
    token: str = Query(..., min_length=6),
    db: Session = Depends(get_db),
):
    ip, ua = _client_meta(request)
    try:
        return {
            "ok": True,
            **FeedbackWebSurveyService.save_callback_consent(
                db,
                session_id=session_id,
                token=token,
                consent=bool(payload.get("consent") or payload.get("callback_consent")),
                phone=(str(payload.get("phone") or payload.get("visitor_phone") or "").strip() or None),
                ip_address=ip,
                user_agent=ua,
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/survey/sessions/{session_id}/reason")
def submit_web_reason(
    session_id: str,
    payload: dict,
    token: str = Query(..., min_length=6),
    db: Session = Depends(get_db),
):
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="reason required")
    try:
        return {
            "ok": True,
            **FeedbackWebSurveyService.save_low_reason_for_previous_step(
                db,
                session_id=session_id,
                token=token,
                reason=reason,
                reason_source=str(payload.get("reason_source") or "text"),
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/survey/sessions/{session_id}/back")
def go_back_web(
    session_id: str,
    token: str = Query(..., min_length=6),
    db: Session = Depends(get_db),
):
    try:
        return {"ok": True, **FeedbackWebSurveyService.step_back(db, session_id, token=token)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/survey/sessions/{session_id}/status")
def web_session_status(
    session_id: str,
    token: str = Query(..., min_length=6),
    db: Session = Depends(get_db),
):
    try:
        return {"ok": True, **FeedbackWebSurveyService.session_status(db, session_id, token=token)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/survey/sessions/{session_id}/voice")
async def submit_web_voice(
    session_id: str,
    file: UploadFile = File(...),
    mode: str = Form("answer"),
    answer: str | None = Form(None),
    token: str = Query(..., min_length=6),
    db: Session = Depends(get_db),
):
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio upload")
    if len(audio_bytes) > _MAX_VOICE_BYTES:
        raise HTTPException(status_code=413, detail="Voice note too large")
    clean_mode = str(mode).strip().lower()
    try:
        return {
            "ok": True,
            **FeedbackWebSurveyService.submit_voice(
                db,
                session_id=session_id,
                token=token,
                audio_bytes=audio_bytes,
                filename=file.filename or "voice.webm",
                content_type=file.content_type or "audio/webm",
                mode=(
                    clean_mode
                    if clean_mode in {"reason", "transcribe", "reason_prev"}
                    else "answer"
                ),
                answer=answer,
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
