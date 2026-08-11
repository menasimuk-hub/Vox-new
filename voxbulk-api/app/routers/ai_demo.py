"""Public + admin API for the AI Demo Agent."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.admin_rbac import require_platform_admin
from app.core.database import get_db, get_sessionmaker
from app.models.user import User
from app.services.ai_demo_service import AiDemoError, AiDemoService
from app.services.telnyx_webhook_security import TelnyxWebhookVerificationError, verify_telnyx_webhook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai-demo", tags=["ai-demo"])
admin_router = APIRouter(prefix="/admin/ai-demo", tags=["admin-ai-demo"])


def _http(exc: AiDemoError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


class DemoRequestIn(BaseModel):
    contact_name: str = Field(min_length=2, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    company_name: str = Field(min_length=2, max_length=255)
    whatsapp: str = Field(min_length=6, max_length=40)
    website: str = Field(min_length=3, max_length=512)
    preferred_language: str = Field(default="en", max_length=10)
    message: str = Field(min_length=10, max_length=4000)
    callback_consent: bool = False
    website_hp: str | None = Field(default="", description="Honeypot")


class ManualDemoIn(BaseModel):
    contact_name: str = ""
    email: str
    company_name: str = "—"
    whatsapp: str | None = None
    website: str | None = "https://voxbulk.com"
    preferred_language: str = "en"
    message: str | None = None
    lead_sales_task_id: str | None = None
    subject_override: str | None = None
    body_override: str | None = None
    skip_wa: bool = False
    voice_region: str | None = None


class BatchRecipientIn(BaseModel):
    email: str
    contact_name: str | None = None
    company_name: str | None = None
    whatsapp: str | None = None
    website: str | None = None
    preferred_language: str | None = None
    message: str | None = None
    voice_region: str | None = None


class BatchDemoIn(BaseModel):
    emails_text: str | None = None
    recipients: list[BatchRecipientIn] | None = None
    preferred_language: str = "en"
    message: str | None = None
    skip_wa: bool = True
    voice_region: str | None = None


class ApproveIn(BaseModel):
    subject_override: str | None = None
    body_override: str | None = None
    skip_wa: bool = False
    voice_region: str | None = None


class RejectIn(BaseModel):
    reason: str | None = None


class StartSessionIn(BaseModel):
    session_id: str
    selected_services: list[str] | None = None


class CompleteIn(BaseModel):
    session_id: str
    summary: str | None = None
    transcript: str | None = None
    recording_path: str | None = None
    duration_seconds: int | None = None


class LiveDemoResponseIn(BaseModel):
    session_id: str
    service: str = "feedback"
    score: int | None = None
    comment: str | None = None
    name: str | None = None
    company: str | None = None
    location: str | None = None


class SettingsIn(BaseModel):
    provider_agent_id: str | None = None
    agent_by_region: dict[str, str] | None = None
    default_voice: str | None = None
    soft_cap_minutes: int | None = None
    from_email: str | None = None
    notes: str | None = None


class KbUpdateIn(BaseModel):
    title: str | None = None
    system_prompt: str | None = None
    fact_sheet: str | None = None
    demo_script: str | None = None
    tool_subset: list[str] | None = None
    is_active: bool | None = None


@router.post("/requests")
def create_demo_request(payload: DemoRequestIn, db: Session = Depends(get_db)):
    try:
        req = AiDemoService.create_web_request(
            db,
            contact_name=payload.contact_name,
            email=payload.email,
            company_name=payload.company_name,
            whatsapp=payload.whatsapp,
            website=payload.website,
            preferred_language=payload.preferred_language,
            message=payload.message,
            honeypot=payload.website_hp,
            callback_consent=bool(payload.callback_consent),
        )
    except AiDemoError as exc:
        raise _http(exc) from exc
    if req is None:
        return {"ok": True, "skipped": True}
    return {"ok": True, "id": req.id, "status": req.status}


@router.get("/verify")
def verify_demo_token(token: str = Query(...), db: Session = Depends(get_db)):
    try:
        return AiDemoService.verify_token(db, token)
    except AiDemoError as exc:
        raise _http(exc) from exc


@router.post("/resend")
def public_resend_demo(
    request_id: str = Query(..., alias="request"),
    sig: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        result = AiDemoService.public_resend(db, request_id=request_id, sig=sig)
        return {"ok": True, "email_sent": True, "request_id": result["request"]["id"]}
    except AiDemoError as exc:
        raise _http(exc) from exc


@router.get("/resend")
def public_resend_demo_get(
    request_id: str = Query(..., alias="request"),
    sig: str = Query(...),
    db: Session = Depends(get_db),
):
    return public_resend_demo(request_id=request_id, sig=sig, db=db)


@router.post("/start-session")
def start_demo_session(payload: StartSessionIn, db: Session = Depends(get_db)):
    try:
        return AiDemoService.start_session(
            db,
            session_id=payload.session_id,
            selected_services=payload.selected_services,
        )
    except AiDemoError as exc:
        raise _http(exc) from exc


@router.get("/walkthrough/{session_id}")
def get_walkthrough(
    session_id: str,
    service: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        return AiDemoService.get_walkthrough_data(db, session_id=session_id, service=service)
    except AiDemoError as exc:
        raise _http(exc) from exc


@router.post("/live-response")
def post_live_demo_response(payload: LiveDemoResponseIn, db: Session = Depends(get_db)):
    try:
        return AiDemoService.submit_live_demo_response(
            db,
            session_id=payload.session_id,
            service=payload.service,
            score=payload.score,
            comment=payload.comment,
            name=payload.name,
            company=payload.company,
            location=payload.location,
        )
    except AiDemoError as exc:
        raise _http(exc) from exc


@router.get("/events/{session_id}")
def poll_demo_events(
    session_id: str,
    after_id: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        return {"events": AiDemoService.poll_events(db, session_id=session_id, after_id=after_id)}
    except AiDemoError as exc:
        raise _http(exc) from exc


@router.get("/sessions/{session_id}/status")
def demo_session_status(session_id: str, db: Session = Depends(get_db)):
    try:
        return AiDemoService.session_gate(db, session_id=session_id)
    except AiDemoError as exc:
        raise _http(exc) from exc


@router.post("/complete")
def complete_demo(payload: CompleteIn, db: Session = Depends(get_db)):
    try:
        return AiDemoService.complete_session(
            db,
            session_id=payload.session_id,
            summary=payload.summary,
            transcript=payload.transcript,
            recording_path=payload.recording_path,
            duration_seconds=payload.duration_seconds,
        )
    except AiDemoError as exc:
        raise _http(exc) from exc


@router.websocket("/events/ws/{session_id}")
async def demo_events_ws(websocket: WebSocket, session_id: str):
    import asyncio

    await websocket.accept()
    after_id: str | None = None
    try:
        while True:
            sm = get_sessionmaker()
            with sm() as db:
                try:
                    events = AiDemoService.poll_events(db, session_id=session_id, after_id=after_id)
                except AiDemoError as exc:
                    await websocket.send_json({"error": exc.message})
                    break
            if events:
                await websocket.send_json({"events": events})
                after_id = str(events[-1].get("id") or after_id)
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=1.5)
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception("demo_events_ws_failed")
        try:
            await websocket.close()
        except Exception:
            pass


async def _verified_tool_payload(request: Request, db: Session) -> dict[str, Any]:
    raw = await request.body()
    try:
        verify_telnyx_webhook(
            raw,
            signature_header=request.headers.get("telnyx-signature-ed25519"),
            timestamp_header=request.headers.get("telnyx-timestamp"),
            db=db,
        )
    except TelnyxWebhookVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    try:
        import json

        return json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return {}


@router.post("/tools/{tool_name}")
async def demo_tool_webhook(tool_name: str, request: Request, db: Session = Depends(get_db)):
    payload = await _verified_tool_payload(request, db)
    if not isinstance(payload, dict):
        payload = {}
    # Bind session from query string when Telnyx omits dynamic variables.
    q_session = str(request.query_params.get("session_id") or "").strip()
    if q_session and not payload.get("session_id"):
        payload = {**payload, "session_id": q_session, "_query_session_id": q_session}
    logger.info(
        "demo_tool_hit tool=%s session=%s keys=%s",
        tool_name,
        payload.get("session_id") or (payload.get("dynamic_variables") or {}).get("demo_session_id"),
        list(payload.keys())[:20],
    )
    result = AiDemoService.handle_tool(db, tool_name=tool_name, payload=payload)
    return result


@router.get("/tools/{tool_name}")
@router.head("/tools/{tool_name}")
async def demo_tool_probe(tool_name: str):
    return {"ok": True, "tool": tool_name}


# --- Admin ---


@admin_router.get("/requests")
def admin_list_requests(
    status: str | None = None,
    source: str | None = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
):
    rows = AiDemoService.list_requests(db, status=status, source=source)
    return {"items": [AiDemoService.serialize_request(r) for r in rows]}


@admin_router.get("/requests/{request_id}")
def admin_get_request(
    request_id: str,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
):
    try:
        return AiDemoService.get_request_detail(db, request_id)
    except AiDemoError as exc:
        raise _http(exc) from exc


@admin_router.post("/requests/manual")
def admin_manual_invite(
    payload: ManualDemoIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    try:
        return AiDemoService.create_manual_and_send(
            db,
            contact_name=payload.contact_name,
            email=payload.email,
            company_name=payload.company_name,
            whatsapp=payload.whatsapp,
            website=payload.website,
            preferred_language=payload.preferred_language,
            message=payload.message,
            admin_id=admin.id,
            lead_sales_task_id=payload.lead_sales_task_id,
            subject_override=payload.subject_override,
            body_override=payload.body_override,
            skip_wa=payload.skip_wa,
            voice_region=payload.voice_region,
        )
    except AiDemoError as exc:
        raise _http(exc) from exc


@admin_router.post("/requests/batch")
def admin_batch_invite(
    payload: BatchDemoIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    recipients: list[dict[str, Any]] = []
    if payload.recipients:
        for r in payload.recipients:
            recipients.append(r.model_dump())
    text = str(payload.emails_text or "").strip()
    if text:
        for line in text.replace(",", "\n").splitlines():
            email = line.strip().lower()
            if not email or "@" not in email:
                continue
            if any(str(x.get("email") or "").lower() == email for x in recipients):
                continue
            recipients.append({"email": email})
    try:
        return AiDemoService.batch_send(
            db,
            recipients=recipients,
            admin_id=admin.id,
            preferred_language=payload.preferred_language,
            message=payload.message,
            skip_wa=payload.skip_wa,
            voice_region=payload.voice_region,
        )
    except AiDemoError as exc:
        raise _http(exc) from exc


@admin_router.post("/requests/{request_id}/approve")
def admin_approve(
    request_id: str,
    payload: ApproveIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    try:
        return AiDemoService.approve_and_send(
            db,
            request_id,
            admin_id=admin.id,
            subject_override=payload.subject_override,
            body_override=payload.body_override,
            skip_wa=payload.skip_wa,
            voice_region=payload.voice_region,
        )
    except AiDemoError as exc:
        raise _http(exc) from exc


@admin_router.post("/requests/{request_id}/reject")
def admin_reject(
    request_id: str,
    payload: RejectIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    try:
        req = AiDemoService.reject_request(db, request_id, reason=payload.reason, admin_id=admin.id)
        return AiDemoService.serialize_request(req)
    except AiDemoError as exc:
        raise _http(exc) from exc


@admin_router.post("/requests/{request_id}/resend")
def admin_resend(
    request_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    try:
        return AiDemoService.admin_resend(db, request_id, admin_id=admin.id)
    except AiDemoError as exc:
        raise _http(exc) from exc


@admin_router.get("/settings")
def admin_get_settings(db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    return AiDemoService.serialize_settings(AiDemoService.get_settings(db))


@admin_router.put("/settings")
def admin_put_settings(
    payload: SettingsIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
):
    row = AiDemoService.update_settings(db, payload.model_dump(exclude_unset=True))
    return AiDemoService.serialize_settings(row)


@admin_router.get("/agents")
def admin_list_demo_agents(db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    return {"items": AiDemoService.list_voice_agents(db)}


@admin_router.post("/agents/duplicate-for-demo")
def admin_duplicate_demo_agents(
    dry_run: bool = False,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
):
    try:
        return AiDemoService.duplicate_region_agents_for_demo(db, dry_run=dry_run)
    except AiDemoError as exc:
        raise _http(exc) from exc


@admin_router.post("/agents/sync-telnyx-tools")
def admin_sync_demo_telnyx_tools(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
):
    from app.services.ai_demo_telnyx_tools import sync_tools_for_all_ai_demo_agents

    return sync_tools_for_all_ai_demo_agents(db)


@admin_router.post("/ensure-demo-org")
def admin_ensure_demo_org(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
):
    from app.services.ai_demo_org_service import AiDemoOrgService

    return AiDemoOrgService.ensure_demo_org(db)


@admin_router.post("/knowledge-bases/upsert-defaults")
def admin_upsert_kb_defaults(db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    result = AiDemoService.upsert_knowledge_bases(db)
    return {**result, "items": AiDemoService.list_knowledge_bases(db)}


@admin_router.get("/knowledge-bases")
def admin_list_kbs(db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    return {"items": AiDemoService.list_knowledge_bases(db)}


@admin_router.put("/knowledge-bases/{service_code}")
def admin_update_kb(
    service_code: str,
    payload: KbUpdateIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
):
    try:
        items = AiDemoService.update_knowledge_base(db, service_code, payload.model_dump(exclude_unset=True))
        return {"items": items}
    except AiDemoError as exc:
        raise _http(exc) from exc


@admin_router.get("/invite-preview")
def admin_invite_preview(db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    from app.data.ai_demo_email_default import DEMO_INVITE_EMAIL_BODY, DEMO_INVITE_EMAIL_SUBJECT
    from app.services.email_template_service import EmailTemplateService

    EmailTemplateService.ensure_system_templates(db)
    subject, body, _ = EmailTemplateService.get_send_content(db, key="demo_invite")
    return {
        "subject": subject or DEMO_INVITE_EMAIL_SUBJECT,
        "body": body or DEMO_INVITE_EMAIL_BODY,
    }
