"""Public AI demo invite open/click tracking (no auth)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.services.ai_demo_service import AiDemoService

router = APIRouter(prefix="/public/ai-demo", tags=["public-ai-demo"])

_PIXEL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00"
    b",\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


@router.get("/o/{tracking_token}.gif")
def track_demo_open(tracking_token: str, db: Session = Depends(get_db)):
    try:
        AiDemoService.record_open(db, tracking_token)
    except Exception:
        pass
    return Response(
        content=_PIXEL_GIF,
        media_type="image/gif",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.get("/c/{tracking_token}")
def track_demo_click(
    tracking_token: str,
    u: str = Query("", description="Destination URL"),
    db: Session = Depends(get_db),
):
    dest = AiDemoService.record_click_and_destination(db, tracking_token, u)
    return RedirectResponse(url=dest, status_code=302)


@router.get("/health")
def public_ai_demo_health():
    origin = (get_settings().public_app_origin or "https://voxbulk.com").rstrip("/")
    return {"ok": True, "demo_origin": origin}
