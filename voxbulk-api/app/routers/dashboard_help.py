from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.services.providers.openai_service import OpenAIProviderService

router = APIRouter(prefix="/dashboard/help", tags=["dashboard-help"])

HELP_SYSTEM_PROMPT = (
    "You are VOXBULK Help Assistant. You ONLY help users navigate and use the VOXBULK dashboard: "
    "surveys, interviews, uploading contact CSV files, pricing quotes, cash payment approval, "
    "starting campaigns, packages, billing, and settings. "
    "Do not answer general knowledge, coding, or unrelated questions. "
    "If asked something outside VOXBULK, politely redirect to VOXBULK features or support."
)


@router.post("/chat")
def help_chat(payload: dict, db: Session = Depends(get_db), _principal=Depends(get_current_principal)):
    message = str(payload.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="message required")
    history = payload.get("history") or []
    transcript = ""
    if isinstance(history, list):
        for item in history[-8:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "user")
            text = str(item.get("text") or item.get("content") or "").strip()
            if text:
                transcript += f"{role.upper()}: {text}\n"
    prompt = f"{HELP_SYSTEM_PROMPT}\n\nConversation so far:\n{transcript}\nUSER: {message}\nASSISTANT:"
    try:
        result = OpenAIProviderService.test_completion_raw(db, prompt=prompt, provider="deepseek")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Help assistant unavailable: {e}") from e
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result)
    return {"ok": True, "reply": str(result.get("assistant_text") or result.get("text") or "").strip()}
