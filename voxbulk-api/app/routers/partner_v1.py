from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from urllib.parse import quote

from app.core.database import get_db
from app.core.config import get_settings
from app.schemas.partner import (
    PartnerHealthOut,
    PartnerResultIn,
    PartnerResultOut,
    PartnerScreeningCreateIn,
    PartnerScreeningCreateOut,
)
from app.services.partner_service import PartnerPrincipal, PartnerService, require_partner_principal, _loads
from app.services.zoho_recruit_connection_service import oauth_complete

router = APIRouter(prefix="/partner/v1", tags=["partner-v1"])


@router.get("/health", response_model=PartnerHealthOut)
def partner_health():
    return PartnerHealthOut(status="ok")


@router.post("/screenings", response_model=PartnerScreeningCreateOut)
def create_partner_screening(
    body: PartnerScreeningCreateIn,
    db: Session = Depends(get_db),
    principal: PartnerPrincipal = Depends(require_partner_principal),
):
    row = PartnerService.create_screening(
        db,
        principal,
        partner_reference_id=body.partner_reference_id,
        job_title=body.job_title,
        screening_questions=body.screening_questions,
        candidate_name=body.candidate_name,
        candidate_phone=body.candidate_phone,
        preferred_language=body.preferred_language,
        callback_url=body.callback_url,
        job_description=body.job_description,
        candidate_email=body.candidate_email,
    )
    return PartnerScreeningCreateOut(
        status=row.status,
        screening_id=row.id,
        partner_reference_id=row.partner_reference_id,
        screening_link=row.screening_link,
        estimated_completion_minutes=row.estimated_completion_minutes,
    )


@router.post("/results", response_model=PartnerResultOut)
def log_partner_result(
    body: PartnerResultIn,
    db: Session = Depends(get_db),
    principal: PartnerPrincipal = Depends(require_partner_principal),
):
    row = PartnerService.log_result(
        db,
        principal,
        partner_reference_id=body.partner_reference_id,
        candidate_score=body.candidate_score,
        result_status=body.status,
        report_url=body.report_url,
        call_duration_minutes=body.call_duration_minutes,
        total_charge_amount=body.total_charge_amount,
        screening_id=body.screening_id,
    )
    return PartnerResultOut(
        status="received",
        received=True,
        screening_id=row.id,
        partner_reference_id=row.partner_reference_id,
    )


@router.get("/oauth/zoho/callback")
def zoho_recruit_oauth_callback(
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
    db: Session = Depends(get_db),
):
    """Zoho API Console redirect — stores Recruit tokens on the mapped org."""
    origin = str(get_settings().admin_app_origin or "https://admin.voxbulk.com").rstrip("/")
    dest_base = f"{origin}/partners/zoho"
    if error:
        msg = str(error_description or error).strip() or "Zoho authorization was denied"
        return RedirectResponse(url=f"{dest_base}?oauth=error&message={quote(msg[:200])}")
    try:
        p = PartnerService.get_provider(db, "zoho")
        if p is None:
            raise ValueError("Zoho partner provider not found")
        cfg = _loads(p.config_json, {})
        oauth_complete(db, code=code, state=state, partner_config=cfg if isinstance(cfg, dict) else {})
    except Exception as exc:
        return RedirectResponse(url=f"{dest_base}?oauth=error&message={quote(str(exc)[:200])}")
    return RedirectResponse(url=f"{dest_base}?oauth=connected")
