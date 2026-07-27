"""Public AI Team / Apify outreach redirects (no auth) — opens, clicks, trial CTA + unsubscribe."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.ai_team_campaign_service import AiTeamCampaignService

router = APIRouter(prefix="/public/ai-team", tags=["public-ai-team"])

# 1x1 transparent GIF
_PIXEL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00"
    b",\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


@router.get("/c/{recipient_id}/o.gif")
def track_open(recipient_id: str, db: Session = Depends(get_db)):
    """Invisible open pixel — records opened_at when the email is viewed."""
    try:
        AiTeamCampaignService.record_open(db, recipient_id)
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


@router.get("/c/{recipient_id}/click")
def track_any_click(
    recipient_id: str,
    u: str = Query("", description="Destination URL"),
    db: Session = Depends(get_db),
):
    """Record click on any wrapped link, then redirect to destination."""
    dest = AiTeamCampaignService.record_link_click_and_destination(db, recipient_id, u)
    return RedirectResponse(url=dest, status_code=302)


@router.get("/c/{recipient_id}/trial")
def track_trial_click(recipient_id: str, db: Session = Depends(get_db)):
    """Record who clicked Start Free Trial, then forward to signup with Expo promo."""
    dest = AiTeamCampaignService.record_trial_click_and_destination(db, recipient_id)
    return RedirectResponse(url=dest, status_code=302)


@router.get("/c/{recipient_id}/unsubscribe")
def unsubscribe_recipient(recipient_id: str, db: Session = Depends(get_db)):
    """One-click opt-out from Apify / AI Team campaign emails."""
    result = AiTeamCampaignService.process_unsubscribe(db, recipient_id)
    return HTMLResponse(content=result["html"], status_code=200)


@router.get("/unsubscribe/demo")
def unsubscribe_demo():
    """Preview/sample unsubscribe confirmation (no DB write)."""
    return HTMLResponse(
        content=AiTeamCampaignService.unsubscribe_confirmation_html(),
        status_code=200,
    )
