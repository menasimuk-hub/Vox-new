from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_AI_TEAM, require_cap
from app.core.database import get_db
from app.models.user import User
from app.services.ai_team_service import AiTeamService, AiTeamServiceError
from app.services.apollo_service import ApolloService, ApolloServiceError
from app.services.provider_settings import ProviderSettingsService
from app.services.resend_service import ResendService, ResendServiceError

router = APIRouter(prefix="/admin/ai-team", tags=["admin-ai-team"])


def _err(exc: Exception) -> HTTPException:
    if isinstance(exc, (AiTeamServiceError, ApolloServiceError, ResendServiceError, ValueError)):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@router.get("/dashboard")
def get_dashboard(db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    stats = AiTeamService.dashboard_stats(db)
    settings = AiTeamService.settings_to_dict(db, AiTeamService.get_settings(db))
    pending = [AiTeamService.prospect_to_dict(db, p) for p in AiTeamService.list_prospects(db, status="pending")]
    return {"stats": stats, "settings": settings, "queue": pending}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    row = AiTeamService.get_settings(db)
    return {"settings": AiTeamService.settings_to_dict(db, row)}


@router.put("/settings")
def put_settings(body: dict[str, Any], db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    row = AiTeamService.update_settings(db, body)
    if body.get("apollo_api_key"):
        AiTeamService.save_provider_keys(db, apollo_api_key=body.get("apollo_api_key"))
    if body.get("resend_api_key"):
        AiTeamService.save_provider_keys(db, resend_api_key=body.get("resend_api_key"))
    return {"settings": AiTeamService.settings_to_dict(db, row)}


@router.get("/prospects")
def list_prospects(
    status: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_cap(CAP_AI_TEAM)),
):
    rows = AiTeamService.list_prospects(db, status=status, q=q)
    return {"prospects": [AiTeamService.prospect_to_dict(db, r) for r in rows]}


@router.get("/prospects/{prospect_id}")
def get_prospect(prospect_id: str, db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    from app.models.ai_team_prospect import AiTeamProspect

    row = db.get(AiTeamProspect, prospect_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Prospect not found")
    messages = AiTeamService.list_messages(db, prospect_id)
    return {
        "prospect": AiTeamService.prospect_to_dict(db, row),
        "messages": [
            {
                "id": m.id,
                "direction": m.direction,
                "from_email": m.from_email,
                "to_email": m.to_email,
                "subject": m.subject,
                "body_text": m.body_text,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@router.get("/prospects/{prospect_id}/email-preview")
def prospect_email_preview(prospect_id: str, db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    try:
        return AiTeamService.prospect_email_preview(db, prospect_id)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/template/preview")
def template_preview(body: dict[str, Any], db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    try:
        return AiTeamService.template_preview(
            db,
            template=str(body.get("template") or "").strip() or None,
            use_sample=body.get("use_sample", True) is not False,
        )
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/test/template-email")
def test_template_email(body: dict[str, Any], db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    try:
        return AiTeamService.send_template_test_email(
            db,
            to_email=str(body.get("to_email") or ""),
            prospect_id=str(body.get("prospect_id") or "").strip() or None,
        )
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/import/csv/preview")
async def csv_preview(
    file: UploadFile = File(...),
    _admin: User = Depends(require_cap(CAP_AI_TEAM)),
):
    try:
        raw = await file.read()
        return AiTeamService.parse_csv_preview(raw)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/import/csv")
async def csv_import(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_cap(CAP_AI_TEAM)),
):
    import json as _json

    try:
        mapping_dict = _json.loads(mapping)
        if not isinstance(mapping_dict, dict):
            raise AiTeamServiceError("Invalid field mapping")
        raw = await file.read()
        return AiTeamService.import_csv_prospects(db, raw, mapping_dict)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/prospects/{prospect_id}/approve")
def approve_prospect(prospect_id: str, db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    try:
        row = AiTeamService.approve_prospect(db, prospect_id)
    except Exception as exc:
        raise _err(exc) from exc
    return {"prospect": AiTeamService.prospect_to_dict(db, row)}


@router.post("/prospects/{prospect_id}/reject")
def reject_prospect(prospect_id: str, db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    try:
        row = AiTeamService.reject_prospect(db, prospect_id)
    except Exception as exc:
        raise _err(exc) from exc
    return {"prospect": AiTeamService.prospect_to_dict(db, row)}


@router.post("/prospects/{prospect_id}/regenerate")
def regenerate_prospect(prospect_id: str, db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    try:
        row = AiTeamService.regenerate_draft(db, prospect_id)
    except Exception as exc:
        raise _err(exc) from exc
    return {"prospect": AiTeamService.prospect_to_dict(db, row)}


@router.put("/prospects/{prospect_id}/draft")
def update_draft(
    prospect_id: str,
    body: dict[str, Any],
    db: Session = Depends(get_db),
    _admin: User = Depends(require_cap(CAP_AI_TEAM)),
):
    try:
        row = AiTeamService.update_draft(db, prospect_id, subject=str(body.get("subject") or ""), body=str(body.get("body") or ""))
    except Exception as exc:
        raise _err(exc) from exc
    return {"prospect": AiTeamService.prospect_to_dict(db, row)}


@router.post("/prospects/{prospect_id}/convert")
def convert_prospect(prospect_id: str, db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    try:
        row = AiTeamService.mark_converted(db, prospect_id)
    except Exception as exc:
        raise _err(exc) from exc
    return {"prospect": AiTeamService.prospect_to_dict(db, row)}


@router.post("/prospects/approve-all")
def approve_all(db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    pending = AiTeamService.list_prospects(db, status="pending")
    approved = []
    errors = []
    for p in pending:
        try:
            AiTeamService.approve_prospect(db, p.id)
            approved.append(p.id)
        except Exception as exc:
            errors.append({"id": p.id, "error": str(exc)})
    return {"approved": approved, "errors": errors}


@router.post("/search")
def run_search(body: dict[str, Any], db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    preview = bool(body.get("preview"))
    limit = int(body.get("limit") or (5 if preview else 0)) or None
    try:
        result = AiTeamService.fetch_prospects(db, preview=preview, limit=limit)
    except Exception as exc:
        raise _err(exc) from exc
    return result


@router.post("/agent/run")
def run_agent(db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    return AiTeamService.run_agent(db)


@router.get("/replies")
def list_replies(db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    rows = AiTeamService.list_replies(db)
    return {"threads": [AiTeamService.prospect_to_dict(db, r) for r in rows]}


@router.post("/replies/{prospect_id}/send")
def send_reply(
    prospect_id: str,
    body: dict[str, Any],
    db: Session = Depends(get_db),
    _admin: User = Depends(require_cap(CAP_AI_TEAM)),
):
    try:
        AiTeamService.send_reply(db, prospect_id, body=str(body.get("body") or ""))
    except Exception as exc:
        raise _err(exc) from exc
    return get_prospect(prospect_id, db, _admin)


@router.get("/analytics")
def analytics(db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    return AiTeamService.analytics(db)


@router.get("/promo-codes")
def promo_codes(db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    return {"promo_codes": AiTeamService.list_promo_codes(db)}


@router.post("/test/apollo")
def test_apollo(body: dict[str, Any], db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    key = str(body.get("api_key") or "").strip()
    if not key:
        cfg, _ = ProviderSettingsService.get_platform_config_decrypted(db, provider="apollo")
        key = str((cfg or {}).get("api_key") or "").strip()
    try:
        return ApolloService.test_connection(key)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/test/resend")
def test_resend(body: dict[str, Any], db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    settings = AiTeamService.get_settings(db)
    to_email = str(body.get("to_email") or "").strip()
    if to_email:
        try:
            return AiTeamService.send_template_test_email(db, to_email=to_email, prospect_id=None)
        except Exception as exc:
            raise _err(exc) from exc
    key = str(body.get("api_key") or "").strip()
    if not key:
        key = AiTeamService._resend_key(db)
    from_email = AiTeamService._from_address(settings)
    fallback_to = str(settings.reply_to_email or settings.from_email or "").strip()
    try:
        return ResendService.test_connection(key, from_email=from_email, to_email=fallback_to)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/test/smtp")
def test_smtp(body: dict[str, Any], db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    settings = AiTeamService.get_settings(db)
    if body:
        AiTeamService.update_settings(db, body)
        settings = AiTeamService.get_settings(db)
    to_email = str(body.get("to_email") or settings.inbox_email or "").strip()
    try:
        return AiTeamService.test_smtp(settings, to_email=to_email, db=db)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/test/email-account")
def test_email_account(body: dict[str, Any], db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    """Send test via Resend using current from/reply-to settings."""
    if body:
        AiTeamService.update_settings(db, body)
    settings = AiTeamService.get_settings(db)
    key = AiTeamService._resend_key(db)
    to_email = str(body.get("to_email") or settings.inbox_email or settings.reply_to_email or "").strip()
    from_email = AiTeamService._from_address(settings)
    try:
        return ResendService.test_connection(key, from_email=from_email, to_email=to_email)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/test/deepseek-sample")
def test_deepseek_sample(db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    try:
        return AiTeamService.generate_sample_email(db)
    except Exception as exc:
        raise _err(exc) from exc
