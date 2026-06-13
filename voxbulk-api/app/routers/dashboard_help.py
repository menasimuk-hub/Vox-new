from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import CurrentPrincipal, get_current_principal
from app.schemas.assistant import AssistantChatIn, AssistantChatOut, AssistantHistoryItem
from app.services.assistant.orchestrator import AssistantOrchestrator

router = APIRouter(prefix="/dashboard/help", tags=["dashboard-help"])


@router.post("/chat", response_model=AssistantChatOut)
def help_chat(
    payload: dict,
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(get_current_principal),
) -> AssistantChatOut:
    """Legacy path — delegates to the grounded application-aware assistant."""
    message = str(payload.get("message") or "").strip()
    if not message:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="message required")
    history_raw = payload.get("history") or []
    history: list[AssistantHistoryItem] = []
    if isinstance(history_raw, list):
        for item in history_raw[-8:]:
            if not isinstance(item, dict):
                continue
            history.append(
                AssistantHistoryItem(
                    role=str(item.get("role") or "user"),
                    text=str(item.get("text") or item.get("content") or "").strip(),
                )
            )
    req = AssistantChatIn(message=message or "help", history=history)
    return AssistantOrchestrator.handle_chat(db, principal=principal, payload=req, is_admin=False)
