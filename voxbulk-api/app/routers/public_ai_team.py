"""Public AI Team / Apify outreach redirects (no auth) — trial CTA + unsubscribe."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.ai_team_campaign_service import AiTeamCampaignService

router = APIRouter(prefix="/public/ai-team", tags=["public-ai-team"])


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
