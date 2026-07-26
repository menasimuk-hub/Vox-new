from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_AI_TEAM, require_cap
from app.core.database import get_db
from app.models.user import User
from app.services.ai_team_service import AiTeamService, AiTeamServiceError
from app.services.apollo_service import ApolloService, ApolloServiceError
from app.services.apify_service import ApifyService, ApifyServiceError
from app.services.provider_settings import ProviderSettingsService
from app.services.resend_service import ResendService, ResendServiceError

router = APIRouter(prefix="/admin/ai-team", tags=["admin-ai-team"])


def _err(exc: Exception) -> HTTPException:
    if isinstance(exc, (AiTeamServiceError, ApolloServiceError, ResendServiceError, ApifyServiceError, ValueError)):
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
    # Secrets first (own commit via provider_configs) so a later settings UPDATE
    # cannot leave Apollo/Resend keys unsaved. Apify is validated inside update_settings.
    if body.get("apollo_api_key"):
        AiTeamService.save_provider_keys(db, apollo_api_key=body.get("apollo_api_key"))
    if body.get("resend_api_key"):
        AiTeamService.save_provider_keys(db, resend_api_key=body.get("resend_api_key"))
    row = AiTeamService.update_settings(db, body)
    return {"settings": AiTeamService.settings_to_dict(db, row)}


@router.get("/prospects")
def list_prospects(
    status: str | None = None,
    q: str | None = None,
    source: str | None = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_cap(CAP_AI_TEAM)),
):
    rows = AiTeamService.list_prospects(db, status=status, q=q, source=source)
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


@router.post("/import/emails")
def import_emails(body: dict[str, Any], db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    try:
        return AiTeamService.import_emails_text(
            db,
            str(body.get("emails") or body.get("text") or ""),
            company_name=str(body.get("company_name") or "").strip(),
            sector=str(body.get("sector") or "").strip(),
            source=str(body.get("source") or "paste").strip() or "paste",
        )
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/apify/runs")
def start_apify_run(body: dict[str, Any], db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    try:
        return AiTeamService.start_apify_run(
            db,
            expo_url=str(body.get("expo_url") or body.get("url") or ""),
            actor_id=str(body.get("actor_id") or "").strip() or None,
        )
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/scrape/directory")
def scrape_directory(body: dict[str, Any], db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    """Built-in exhibitor directory scrape (Easyfairs / HTML). No Apify actor required."""
    try:
        # Default ON — few Easyfairs stands publish email in the description;
        # company websites yield most addresses (slower: ~2–5 min for ~200 stands).
        follow_raw = body.get("follow_websites")
        follow_websites = True if follow_raw is None else bool(follow_raw)
        return AiTeamService.start_directory_scrape(
            db,
            expo_url=str(body.get("expo_url") or body.get("url") or ""),
            follow_websites=follow_websites,
            max_stands=int(body.get("max_stands") or 500),
        )
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/apify/runs")
def list_apify_runs(db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    return {"runs": AiTeamService.list_apify_runs(db)}


@router.delete("/apify/runs")
def purge_apify_runs(db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    """Remove all scrape / Apify run history (URLs + stored results). Imported prospects are kept."""
    try:
        return AiTeamService.purge_apify_runs(db)
    except Exception as exc:
        raise _err(exc) from exc


@router.delete("/apify/runs/{run_id}")
def delete_apify_run(run_id: str, db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    try:
        return AiTeamService.delete_apify_run(db, run_id)
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/apify/runs/{run_id}")
def get_apify_run(run_id: str, db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    try:
        return AiTeamService.refresh_apify_run(db, run_id)
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/apify/runs/{run_id}/preview")
def preview_apify_run(run_id: str, db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    try:
        return AiTeamService.preview_apify_run(db, run_id)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/apify/runs/{run_id}/import")
def import_apify_run(run_id: str, db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    try:
        return AiTeamService.import_apify_run(db, run_id)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/followups/run")
def run_followups(db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    try:
        return AiTeamService.process_due_followups(db)
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
    """Send a test via the configured delivery provider (SMTP or Resend)."""
    if body:
        AiTeamService.update_settings(db, body)
    settings = AiTeamService.get_settings(db)
    to_email = str(body.get("to_email") or settings.inbox_email or settings.reply_to_email or settings.from_email or "").strip()
    try:
        return AiTeamService.send_template_test_email(db, to_email=to_email, prospect_id=None)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/test/apify")
def test_apify(body: dict[str, Any], db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    """Validate with Apify first, save only if valid, then re-test the DB-stored token."""
    raw_token = ApifyService.normalize_token(str(body.get("apify_token") or body.get("api_token") or ""))
    raw_user_id = ApifyService.normalize_token(str(body.get("apify_user_id") or body.get("user_id") or ""))
    token_saved = False
    source = "request"
    try:
        if raw_user_id:
            AiTeamService.persist_apify_user_id(db, raw_user_id)

        if raw_token:
            AiTeamService.persist_apify_token(db, raw_token)
            token_saved = True
            source = "request"
        else:
            settings = AiTeamService.get_settings(db)
            saved = AiTeamService._apify_token(settings, db=db)
            if not saved:
                uid = (settings.apify_user_id or raw_user_id or "").strip()
                if uid:
                    raise AiTeamServiceError(
                        f"User ID saved ({ApifyService.token_fingerprint(uid)}), but Apify still needs "
                        "the Personal API token that starts with apify_api_ "
                        "(Console → Settings → Integrations). User ID alone cannot connect. "
                        "Or use the Scrape tab — no Apify needed for Easyfairs directories."
                    )
                raise AiTeamServiceError(
                    "No Apify token pasted and none saved in DB. "
                    "Paste User ID (optional) + Personal API token (apify_api_…) from "
                    "Apify Console → Settings → Integrations, then click Test."
                )
            ApifyService.test_connection(saved, actor_id=None)
            source = "database"
            token_saved = True

        patch: dict[str, Any] = {}
        if body.get("apify_exhibitor_actor_id") is not None and str(body.get("apify_exhibitor_actor_id") or "").strip():
            patch["apify_exhibitor_actor_id"] = body.get("apify_exhibitor_actor_id")
        if body.get("apify_contact_actor_id") is not None and str(body.get("apify_contact_actor_id") or "").strip():
            patch["apify_contact_actor_id"] = body.get("apify_contact_actor_id")
        if patch:
            try:
                AiTeamService.update_settings(db, patch)
            except Exception:
                pass

        # Always re-test the token loaded from DB — proves persistence.
        check_actor = body.get("check_actor") is True
        result = AiTeamService.test_apify(db, token=None, check_actor=check_actor)
        settings = AiTeamService.get_settings(db)
        configured = AiTeamService._apify_token_configured(db, settings)
        stored = AiTeamService._apify_token(settings, db=db)
        result["token_saved"] = bool(token_saved and configured and stored)
        result["apify_token_configured"] = configured
        result["apify_user_id"] = (settings.apify_user_id or result.get("user_id") or "").strip()
        result["token_source"] = source
        result["token_fingerprint"] = ApifyService.token_fingerprint(stored)
        if result.get("ok") and result["token_saved"]:
            uid_bit = f" · user {result['apify_user_id']}" if result.get("apify_user_id") else ""
            result["message"] = (
                f"{result.get('message') or 'Apify connected'} · "
                f"token saved in DB ({result['token_fingerprint']}){uid_bit}"
            )
        elif result.get("ok") and not result["token_saved"]:
            result["ok"] = False
            result["message"] = "Apify accepted the token but it is NOT saved in the database"
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/test/all")
def test_all(body: dict[str, Any], db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    if body:
        # Persist any in-form credentials before testing
        AiTeamService.update_settings(db, body)
    try:
        return AiTeamService.test_all_connections(
            db, to_email=str(body.get("to_email") or "").strip() or None
        )
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/test/deepseek-sample")
def test_deepseek_sample(db: Session = Depends(get_db), _admin: User = Depends(require_cap(CAP_AI_TEAM))):
    try:
        return AiTeamService.generate_sample_email(db)
    except Exception as exc:
        raise _err(exc) from exc
