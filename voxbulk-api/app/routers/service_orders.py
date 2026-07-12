from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrderRecipient
from app.services.org_service_credit_service import OrgServiceCreditError, OrgServiceCreditService
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService

router = APIRouter(prefix="/service-orders", tags=["service-orders"])


def _interview_draft_payload(db: Session, *, order, recipients, summary, billing) -> dict:
    from app.services.platform_catalog_service import PlatformCatalogService

    return {
        "order": ServiceOrderService.order_to_dict(order) if order is not None else None,
        "recipients": recipients,
        "summary": summary,
        "billing_context": billing,
        **PlatformCatalogService.interview_platform_capabilities(db),
    }


def _require_org_service(db: Session, org_id: str, service_code: str) -> Organisation:
    from app.services.org_enabled_services import (
        is_service_enabled,
        org_service_maps,
        service_code_to_enabled_key,
    )
    from app.services.recovery_service import OrganisationService

    org = OrganisationService.get_org(db, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    key = service_code_to_enabled_key(service_code)
    if key:
        _, _, visible = org_service_maps(org, db)
        if not is_service_enabled(visible, key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Service is not enabled for this organisation",
            )
    return org


def _require_order_service(db: Session, org_id: str, order_id: str) -> tuple[Organisation, object]:
    order = ServiceOrderService.get_order(db, order_id, org_id=org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    org = _require_org_service(db, org_id, str(order.service_code or ""))
    return org, order


@router.get("/catalog")
def list_catalog(db: Session = Depends(get_db), _principal=Depends(get_current_principal)):
    services = PlatformCatalogService.list_services(db)
    return [
        {
            "id": svc.id,
            "code": svc.code,
            "name": svc.name,
            "description": svc.description,
            "service_kind": svc.service_kind,
        }
        for svc in services
    ]


@router.get("/credits")
def get_promo_credits(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    return {"ok": True, **OrgServiceCreditService.balances_dict(org)}


@router.get("/ai-follow-up-jobs/{job_id}/detail")
def get_ai_followup_job_detail(
    job_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.ai_followup_call_media_service import build_ai_followup_call_detail, resolve_ai_followup_job

    try:
        job = resolve_ai_followup_job(db, job_id=job_id, org_id=principal.org_id)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI follow-up job not found")
    return build_ai_followup_call_detail(db, job)


@router.get("/ai-follow-up-jobs/{job_id}/recording")
def get_ai_followup_job_recording(
    job_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from fastapi.responses import RedirectResponse, Response

    from app.services.ai_followup_call_media_service import (
        USER_RECORDING_PROCESSING,
        USER_RECORDING_UNAVAILABLE,
        fetch_ai_followup_recording,
        resolve_ai_followup_job,
    )

    try:
        job = resolve_ai_followup_job(db, job_id=job_id, org_id=principal.org_id)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI follow-up job not found")

    outcome = {}
    try:
        outcome = json.loads(job.outcome_json or "{}")
        if not isinstance(outcome, dict):
            outcome = {}
    except Exception:
        outcome = {}

    remote = str(outcome.get("recording_url") or "").strip()
    if remote.startswith("http://") or remote.startswith("https://"):
        return RedirectResponse(url=remote, status_code=302)

    try:
        result = fetch_ai_followup_recording(db, job)
    except Exception:
        import logging

        logging.getLogger(__name__).exception("ai_followup_recording_fetch_failed job_id=%s", job_id)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=USER_RECORDING_UNAVAILABLE)

    if not result:
        st = str(job.status or "").strip().lower()
        detail = USER_RECORDING_PROCESSING if st == "completed" else USER_RECORDING_UNAVAILABLE
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

    audio_bytes, media_type = result
    return Response(
        content=audio_bytes,
        media_type=media_type,
        headers={"Content-Disposition": 'inline; filename="ai-follow-up-recording.mp3"'},
    )


@router.get("/template.csv")
def download_recipient_template(
    for_: str | None = None,
    _principal=Depends(get_current_principal),
):
    kind = str(for_ or "").strip().lower()
    for_survey = kind in {"survey", "wa", "whatsapp"}
    if for_survey:
        filename = "voxbulk-survey-contacts-template.csv"
    elif kind in {"interview", "ai_interview", "ai-interview"}:
        filename = "voxbulk-interview-contacts-template.csv"
    else:
        filename = "voxbulk-contacts-template.csv"
    return PlainTextResponse(
        ServiceOrderService.recipient_template_csv(for_survey=for_survey),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/template.xlsx")
@router.get("/templates/interview.xlsx")
def download_recipient_template_xlsx(
    for_: str | None = None,
    _principal=Depends(get_current_principal),
):
    kind = str(for_ or "").strip().lower()
    if kind not in {"interview", "ai_interview", "ai-interview", ""}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Excel template is only available for interview contacts. Use template.csv for surveys.",
        )
    try:
        content = ServiceOrderService.recipient_template_xlsx(for_interview=True)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
    filename = "voxbulk-interview-contacts-template.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/quote")
def quote_preview(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    service_code = str(payload.get("service_code") or "")
    _require_org_service(db, principal.org_id, service_code)
    try:
        options = dict(payload.get("options") or {})
        options["org_id"] = principal.org_id
        return PlatformCatalogService.calculate_quote(
            db,
            service_code=service_code,
            recipient_count=int(payload.get("recipient_count") or 0),
            options=options,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/recipients/preview")
async def preview_recipients_file(
    file: UploadFile = File(...),
    service_code: str = Form("interview"),
    delivery: str = Form("ai_call"),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    code = str(service_code or "interview").strip().lower()
    _require_org_service(db, principal.org_id, code)
    content = await file.read()
    try:
        rows = ServiceOrderService.parse_recipient_file(content, file.filename or "upload.csv")
        if not rows:
            raise ValueError("No valid contacts found in file")
        options: dict = {"org_id": principal.org_id}
        if code == "interview":
            options["delivery"] = str(delivery or "ai_call").strip().lower()
        quote = PlatformCatalogService.calculate_quote(
            db,
            service_code=code,
            recipient_count=len(rows),
            options=options,
        )
        preview = [{"name": r.get("name") or "", "phone": r.get("phone") or "", "email": r.get("email") or ""} for r in rows[:8]]
        return {
            "ok": True,
            "recipient_count": len(rows),
            "preview": preview,
            "quote": quote,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("")
def list_my_orders(
    service_code: str | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    if service_code:
        _require_org_service(db, principal.org_id, service_code)
    if service_code == "interview":
        from app.services.interview_intake_service import interview_draft_visible_in_saved_list, purge_empty_interview_drafts
        from sqlalchemy import func

        purge_empty_interview_drafts(db, org_id=principal.org_id)
        rows = ServiceOrderService.list_orders(db, org_id=principal.org_id, service_code=service_code)
        visible: list = []
        for row in rows:
            if row.service_code != "interview" or row.status != "draft" or row.payment_status != "unpaid":
                visible.append(row)
                continue
            count = db.execute(
                select(func.count())
                .select_from(ServiceOrderRecipient)
                .where(ServiceOrderRecipient.order_id == row.id)
            ).scalar_one()
            if interview_draft_visible_in_saved_list(row, recipient_count=int(count or 0)):
                visible.append(row)
        return [ServiceOrderService.order_to_dict(r, db=db) for r in visible]

    rows = ServiceOrderService.list_orders(db, org_id=principal.org_id, service_code=service_code)
    return [ServiceOrderService.order_to_dict(r, db=db) for r in rows]


@router.post("")
def create_order(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    service_code = str(payload.get("service_code") or "")
    _require_org_service(db, principal.org_id, service_code)
    try:
        order = ServiceOrderService.create_order(
            db,
            org_id=principal.org_id,
            user_id=principal.user_id,
            service_code=str(payload.get("service_code") or ""),
            title=str(payload.get("title") or ""),
            config=payload.get("config") or {},
        )
        return ServiceOrderService.order_to_dict(order, db=db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/survey-agents")
def list_survey_agents_for_dashboard(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_org_service(db, principal.org_id, "survey")
    from app.services.survey_voice_agent_service import list_dashboard_agents_for_service
    from app.core.agent_services import SERVICE_SURVEY

    return {
        "agents": list_dashboard_agents_for_service(db, service_key=SERVICE_SURVEY, org_id=principal.org_id),
    }


@router.get("/interview-agents")
def list_interview_agents_for_dashboard(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_org_service(db, principal.org_id, "interview")
    from app.services.survey_voice_agent_service import list_dashboard_agents_for_service
    from app.core.agent_services import SERVICE_INTERVIEW

    return {
        "agents": list_dashboard_agents_for_service(db, service_key=SERVICE_INTERVIEW, org_id=principal.org_id),
    }


@router.get("/interview-agents/{agent_id}/voice-preview")
def preview_interview_agent_voice_route(
    agent_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from fastapi import HTTPException

    from app.services.interview_agent_display_service import preview_interview_agent_voice

    _require_org_service(db, principal.org_id, "interview")
    try:
        return preview_interview_agent_voice(db, agent_id=agent_id, org_id=principal.org_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/interview/billing-context")
def get_interview_billing_context(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.interview_billing_context import org_interview_billing_context

    org = _require_org_service(db, principal.org_id, "interview")
    return org_interview_billing_context(db, org)


@router.get("/interview/cv-collection-limits")
def get_interview_cv_collection_limits(
    order_id: str | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.interview_cv_collection_service import compute_cv_collection_limits

    _require_org_service(db, principal.org_id, "interview")
    exclude = str(order_id or "").strip() or None
    return compute_cv_collection_limits(db, principal.org_id, exclude_order_id=exclude)


@router.get("/interview/draft")
def get_interview_draft(
    order_id: str | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.interview_billing_context import org_interview_billing_context
    from app.services.interview_intake_service import get_latest_interview_draft, intake_summary, list_intake_recipients

    org = _require_org_service(db, principal.org_id, "interview")
    billing = org_interview_billing_context(db, org) if org else {}
    order = None
    requested_id = str(order_id or "").strip()
    if requested_id:
        order = ServiceOrderService.get_order(db, requested_id, org_id=principal.org_id)
        if order is None or order.service_code != "interview":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview order not found")
    if order is None:
        order = get_latest_interview_draft(db, org_id=principal.org_id)
    if order is None:
        return _interview_draft_payload(db, order=None, recipients=[], summary=intake_summary([]), billing=billing)
    recipients = list_intake_recipients(db, order)
    return _interview_draft_payload(
        db,
        order=order,
        recipients=recipients,
        summary=intake_summary(recipients),
        billing=billing,
    )


@router.post("/interview/draft/new")
def create_new_interview_draft_route(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    import logging

    from app.services.interview_intake_service import create_new_interview_draft, intake_summary
    from app.services.interview_billing_context import org_interview_billing_context

    log = logging.getLogger(__name__)
    log.info("interview_draft_new entry org=%s user=%s", principal.org_id, principal.user_id)
    try:
        org = _require_org_service(db, principal.org_id, "interview")
        order = create_new_interview_draft(db, org_id=principal.org_id, user_id=principal.user_id)
        billing = org_interview_billing_context(db, org)
        payload = _interview_draft_payload(db, order=order, recipients=[], summary=intake_summary([]), billing=billing)
        log.info("interview_draft_new ok order_id=%s", order.id)
        return payload
    except HTTPException:
        raise
    except ValueError as e:
        log.warning("interview_draft_new value_error: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        log.exception("interview_draft_new failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not create interview draft: {type(e).__name__}: {e}",
        ) from e


@router.post("/interview/draft/abandon")
def abandon_interview_draft(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.interview_intake_service import abandon_empty_interview_draft

    _require_org_service(db, principal.org_id, "interview")
    order_id = str(payload.get("order_id") or "").strip()
    if not order_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="order_id is required")
    deleted = abandon_empty_interview_draft(db, org_id=principal.org_id, order_id=order_id)
    return {"ok": True, "deleted": deleted}


@router.post("/interview/draft")
def ensure_interview_draft(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.interview_intake_service import ensure_interview_draft_order, intake_summary, list_intake_recipients

    _require_org_service(db, principal.org_id, "interview")
    order_id = str(payload.get("order_id") or "").strip()
    if order_id:
        order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
        if order.service_code != "interview":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not an interview order")
        if order.status in {"running", "completed", "cancelled"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot save draft for a running or finished interview — use schedule updates instead")
    else:
        order = ensure_interview_draft_order(
            db,
            org_id=principal.org_id,
            user_id=principal.user_id,
            title=str(payload.get("title") or "Interview draft"),
            role=str(payload.get("role") or ""),
            criteria=str(payload.get("criteria") or ""),
        )
    from app.services.interview_billing_context import org_interview_billing_context
    from app.services.recovery_service import OrganisationService

    org = OrganisationService.get_org(db, principal.org_id)
    config_patch = payload.get("config")
    if isinstance(config_patch, dict) and config_patch:
        billing = org_interview_billing_context(db, org) if org else {}
        if config_patch.get("cv_email_enabled") and not billing.get("cv_email_allowed"):
            config_patch = dict(config_patch)
            config_patch["cv_email_enabled"] = False
        if "delivery" in config_patch:
            try:
                config_patch = dict(config_patch)
                config_patch["delivery"] = PlatformCatalogService.normalize_interview_delivery(
                    db, str(config_patch.get("delivery") or "ai_call")
                )
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if order.service_code == "interview":
            from app.services.interview_cv_collection_service import CvCollectionConfigError, validate_and_apply_cv_config
            from app.services.interview_cv_email_service import _loads_config

            try:
                previous = _loads_config(order)
                config_patch = validate_and_apply_cv_config(
                    db,
                    principal.org_id,
                    order,
                    config_patch,
                    previous_cfg=previous,
                )
            except CvCollectionConfigError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
            from app.services.script_moderation_service import apply_script_moderation_gate

            config_patch = apply_script_moderation_gate(
                service_code=order.service_code,
                config_patch=config_patch,
                previous_cfg=previous,
                db=db,
            )
        order = ServiceOrderService.update_order(db, order, {"config": config_patch})
        if order.service_code == "interview":
            from app.services.interview_email_ats_service import retry_deferred_email_ats

            retry_deferred_email_ats(db, order_id=order.id, limit=20)
    sched_patch = {}
    for key in ("run_mode", "scheduled_start_at", "scheduled_end_at"):
        if key in payload and payload[key] is not None:
            sched_patch[key] = payload[key]
    if sched_patch:
        order = ServiceOrderService.update_order(db, order, sched_patch)
    if payload.get("title"):
        order = ServiceOrderService.update_order(db, order, {"title": str(payload.get("title"))})
    recipients = list_intake_recipients(db, order)
    billing = org_interview_billing_context(db, org) if org else {}
    return _interview_draft_payload(
        db,
        order=order,
        recipients=recipients,
        summary=intake_summary(recipients),
        billing=billing,
    )


@router.get("/interview-reports")
def list_interview_reports(
    period: str = "month",
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.interview_report_service import InterviewReportService

    _require_org_service(db, principal.org_id, "interview")
    return InterviewReportService.list_batches(db, principal.org_id, period=period)


@router.get("/interview-reports/export.csv")
def export_interview_reports_csv(
    period: str = "month",
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.interview_report_service import InterviewReportService

    _require_org_service(db, principal.org_id, "interview")
    from fastapi.responses import Response

    payload = InterviewReportService.list_batches(db, principal.org_id, period=period)
    csv_text = InterviewReportService.export_batches_csv(payload)
    filename = f"interview-batches-{period}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/whatsapp-templates")
def list_whatsapp_templates(
    purpose: str | None = None,
    approved_only: bool = True,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.platform_whatsapp_template_service import PlatformWhatsappTemplateService

    _ = principal
    return PlatformWhatsappTemplateService.list_for_dashboard(db, approved_only=approved_only, purpose=purpose)


@router.post("/whatsapp-templates/sync")
def sync_whatsapp_templates(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.telnyx_whatsapp_template_sync_service import (
        TelnyxWhatsappTemplateSyncError,
        TelnyxWhatsappTemplateSyncService,
    )

    _ = principal
    try:
        return TelnyxWhatsappTemplateSyncService.sync(db)
    except TelnyxWhatsappTemplateSyncError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e


@router.get("/integrations")
def list_org_integrations(
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    """Unified catalogue of integrations visible to the current org."""
    from app.services.integration_catalogue_service import list_integrations_for_org

    return list_integrations_for_org(db, principal.org_id)


@router.post("/integrations/{provider}/test")
def test_org_integration(
    provider: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.integration_test_service import IntegrationTestError, deep_health_check

    try:
        return deep_health_check(db, principal.org_id, provider)
    except IntegrationTestError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/integrations/{provider}/disconnect")
def disconnect_org_integration(
    provider: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.crm_connection_service import disconnect_crm
    from app.services.integration_catalogue_service import (
        BOOKING_GROUP,
        CRM_GROUP,
        resolve_provider_spec,
    )
    from app.services.scheduling_connection_service import disconnect_scheduling

    spec = resolve_provider_spec(provider)
    if spec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown integration: {provider}")
    try:
        if spec.group == BOOKING_GROUP:
            return disconnect_scheduling(db, principal.org_id, provider=spec.key)
        if spec.group == CRM_GROUP:
            return disconnect_crm(db, principal.org_id, provider=spec.key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider is not disconnectable from the dashboard")


@router.get("/{order_id}/recipients")
def list_order_recipients(order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.interview_intake_service import intake_summary, list_intake_recipients

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    recipients = list_intake_recipients(db, order)
    return {"recipients": recipients, "summary": intake_summary(recipients)}


@router.post("/{order_id}/recipients/intake-contacts")
async def intake_contacts_file(
    order_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.interview_intake_service import (
        intake_contacts_csv,
        intake_summary,
        list_intake_recipients,
        parse_contacts_csv_relaxed_from_bytes,
    )

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    content = await file.read()
    try:
        rows = parse_contacts_csv_relaxed_from_bytes(content, file.filename or "upload.csv")
        if not rows:
            raise ValueError("No contacts found in file")
        order = intake_contacts_csv(db, order, rows)
        recipients = list_intake_recipients(db, order)
        return {"order": ServiceOrderService.order_to_dict(order), "recipients": recipients, "summary": intake_summary(recipients)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{order_id}/recipients/intake-files")
async def intake_mixed_uploads(
    order_id: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.interview_intake_service import intake_mixed_files

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload at least one file")
    payload: list[tuple[str, bytes]] = []
    for upload in files:
        payload.append((upload.filename or "upload", await upload.read()))
    try:
        result = intake_mixed_files(db, order, payload)
        order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
        result["order"] = ServiceOrderService.order_to_dict(order)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{order_id}/recipients/intake-cvs")
async def intake_cv_uploads(
    order_id: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.interview_intake_service import intake_cv_files

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload at least one CV file")
    payload: list[tuple[str, bytes]] = []
    for upload in files:
        payload.append((upload.filename or "cv.pdf", await upload.read()))
    try:
        result = intake_cv_files(db, order, payload)
        order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
        result["order"] = ServiceOrderService.order_to_dict(order)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.patch("/{order_id}/recipients/{recipient_id}")
def patch_recipient(
    order_id: str,
    recipient_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.interview_intake_service import list_intake_recipients, recipient_intake_dict, update_intake_recipient

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    recipient = ServiceOrderService.get_recipient(db, order.id, recipient_id)
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    try:
        if order.service_code == "interview":
            updated = update_intake_recipient(db, order, recipient, payload or {})
            recipients = list_intake_recipients(db, order)
            from app.services.interview_intake_service import intake_summary

            return {
                "recipient": recipient_intake_dict(updated),
                "recipients": recipients,
                "summary": intake_summary(recipients),
            }
        updated = ServiceOrderService.update_recipient(db, order, recipient, payload or {})
        return {"recipient": ServiceOrderService.recipient_to_dict(updated)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.delete("/{order_id}/recipients/{recipient_id}")
def remove_recipient(
    order_id: str,
    recipient_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.interview_intake_service import delete_intake_recipient, intake_summary, list_intake_recipients

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    recipient = ServiceOrderService.get_recipient(db, order.id, recipient_id)
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    try:
        if order.service_code == "interview":
            order = delete_intake_recipient(db, order, recipient)
            recipients = list_intake_recipients(db, order)
            return {
                "ok": True,
                "order": ServiceOrderService.order_to_dict(order),
                "recipients": recipients,
                "summary": intake_summary(recipients),
            }
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Delete is only supported for interview intake")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{order_id}/recipients/{recipient_id}/cv")
def download_recipient_cv(
    order_id: str,
    recipient_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from fastapi.responses import FileResponse, Response

    from app.services.career_cv_storage_service import cv_media_type, resolve_cv_path

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.service_code != "interview":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CV download is only for interview orders")
    recipient = ServiceOrderService.get_recipient(db, order.id, recipient_id)
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    path = resolve_cv_path(recipient.cv_storage_key or "")
    if path is not None:
        filename = recipient.cv_filename or path.name
        return FileResponse(path, filename=filename, media_type=cv_media_type(filename))
    text = (recipient.cv_text or "").strip()
    if text:
        from pathlib import Path as PathLib

        base = recipient.cv_filename or "cv.txt"
        stem = PathLib(base).stem or "cv"
        filename = f"{stem}.txt"
        return Response(
            content=text.encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CV file not available for download")


@router.get("/{order_id}")
def get_order(order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _, order = _require_order_service(db, principal.org_id, order_id)
    recipients = ServiceOrderService.get_recipients(db, order.id)
    return ServiceOrderService.order_to_dict(order, include_recipients=True, recipients=recipients, db=db)


@router.post("/{order_id}/archive")
def archive_order(order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.status in {"running", "paused", "scheduled"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot archive a running or scheduled campaign — stop it first",
        )
    if order.status == "archived":
        return ServiceOrderService.order_to_dict(order)
    order.status = "archived"
    from datetime import datetime

    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()
    db.refresh(order)
    return ServiceOrderService.order_to_dict(order)


@router.patch("/{order_id}")
def patch_order(order_id: str, payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        config_patch = payload.get("config") if isinstance(payload.get("config"), dict) else None
        if config_patch and order.service_code == "interview" and config_patch.get("cv_email_enabled"):
            from app.services.interview_billing_context import org_interview_billing_context
            from app.services.recovery_service import OrganisationService

            org = OrganisationService.get_org(db, principal.org_id)
            billing = org_interview_billing_context(db, org) if org else {}
            if not billing.get("cv_email_allowed"):
                payload = dict(payload)
                config_patch = dict(config_patch)
                config_patch["cv_email_enabled"] = False
                payload["config"] = config_patch
        if config_patch and order.service_code == "interview":
            from app.services.interview_cv_collection_service import CvCollectionConfigError, validate_and_apply_cv_config
            from app.services.interview_cv_email_service import _loads_config

            payload = dict(payload)
            config_patch = dict(payload.get("config") or {})
            try:
                config_patch = validate_and_apply_cv_config(
                    db,
                    principal.org_id,
                    order,
                    config_patch,
                    previous_cfg=_loads_config(order),
                )
                payload["config"] = config_patch
            except CvCollectionConfigError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if config_patch and order.service_code in {"interview", "survey"}:
            from app.services.interview_cv_email_service import _loads_config
            from app.services.script_moderation_service import apply_script_moderation_gate

            payload = dict(payload)
            config_patch = dict(payload.get("config") or {})
            previous_cfg = _loads_config(order)
            config_patch = apply_script_moderation_gate(
                service_code=order.service_code,
                config_patch=config_patch,
                previous_cfg=previous_cfg,
                db=db,
            )
            payload["config"] = config_patch
        order = ServiceOrderService.update_order(db, order, payload)
        return ServiceOrderService.order_to_dict(order, db=db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{order_id}/recipients/upload")
async def upload_recipients(
    order_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    content = await file.read()
    try:
        rows = ServiceOrderService.parse_recipient_file(content, file.filename or "upload.csv")
        if not rows:
            raise ValueError("No valid contacts found in file — check name and phone columns.")
        order = ServiceOrderService.replace_recipients(db, order, rows)
        order = ServiceOrderService.quote_order(db, order)
        return ServiceOrderService.order_to_dict(order)
    except ValueError as e:
        import logging

        logging.getLogger(__name__).warning(
            "recipients_upload_rejected order_id=%s filename=%r size=%s err=%s",
            order_id,
            file.filename,
            len(content),
            e,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{order_id}/quote")
def refresh_quote(order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    import logging

    from app.models.organisation import Organisation
    from app.services.billing_currency import currency_symbol, resolve_org_currency
    from app.services.interview_billing_context import org_interview_billing_context

    logger = logging.getLogger(__name__)
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    org = db.get(Organisation, principal.org_id)
    try:
        currency = resolve_org_currency(db, org)
        billing = org_interview_billing_context(db, org) if org else {}
        if order.service_code == "interview" and billing.get("has_active_subscription"):
            payload = ServiceOrderService.order_to_dict(order)
            plan_name = str(billing.get("plan_name") or "your package").strip() or "your package"
            payload["quote_total_pence"] = 0
            payload["quote_total_display"] = f"Included in {plan_name}"
            payload["currency"] = currency
            payload["currency_symbol"] = currency_symbol(currency)
            payload["included_in_package"] = True
            return payload
        order = ServiceOrderService.quote_order(db, order)
        payload = ServiceOrderService.order_to_dict(order)
        from app.services.billing_currency import money_display

        payload["currency"] = currency
        payload["currency_symbol"] = currency_symbol(currency)
        payload["quote_total_display"] = money_display(int(order.quote_total_pence or 0), currency)
        return payload
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.exception("refresh_quote_failed order_id=%s", order_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e) or "Could not calculate quote") from e


@router.post("/{order_id}/pay-promo-credits")
def pay_with_promo_credits(order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    try:
        order = OrgServiceCreditService.apply_to_order(db, order, org)
        return ServiceOrderService.order_to_dict(order)
    except OrgServiceCreditError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{order_id}/launch-eligibility")
def get_survey_launch_eligibility(
    order_id: str,
    refresh: bool = False,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.models.organisation import Organisation
    from app.services.billing_currency import currency_symbol
    from app.services.survey_launch_eligibility_service import SurveyLaunchEligibilityService

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.service_code != "survey":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Launch eligibility is only for survey orders")
    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    try:
        payload = SurveyLaunchEligibilityService.compute_cached(db, order, org, force=refresh)
        payload["currency_symbol"] = currency_symbol(str(payload.get("currency") or "GBP"))
        if payload.get("amount_due_pence"):
            payload["quote_total_pence"] = payload.get("amount_due_pence")
            payload["quote_total_display"] = payload.get("amount_due_display")
        return payload
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{order_id}/interview/launch-eligibility")
def get_interview_launch_eligibility(
    order_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.models.organisation import Organisation
    from app.services.billing_currency import currency_symbol
    from app.services.interview_launch_eligibility_service import InterviewLaunchEligibilityService

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.service_code != "interview":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Launch eligibility is only for interview orders")
    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    try:
        payload = InterviewLaunchEligibilityService.compute(db, order, org)
        payload["currency_symbol"] = currency_symbol(str(payload.get("currency") or "GBP"))
        return payload
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{order_id}/survey/launch")
def launch_survey_campaign(
    order_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    import logging

    from app.models.organisation import Organisation
    from app.services.survey_launch_eligibility_service import SurveyLaunchEligibilityError
    from app.services.survey_launch_service import SurveyLaunchService

    logger = logging.getLogger(__name__)
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    body = payload if isinstance(payload, dict) else {}
    run_now = str(body.get("run_mode") or "now").strip().lower() != "schedule"
    try:
        return SurveyLaunchService.launch(db, order, org, run_now=run_now)
    except SurveyLaunchEligibilityError as e:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.exception("survey_launch_failed order_id=%s org_id=%s", order_id, principal.org_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e) or "Could not launch survey campaign",
        ) from e


@router.delete("/{order_id}")
def delete_order(
    order_id: str,
    confirm_running_delete: bool = False,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        ServiceOrderService.delete_order(db, order, confirm_running_delete=confirm_running_delete)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{order_id}/duplicate")
def duplicate_order(order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.service_code != "survey":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only survey orders can be duplicated")
    try:
        copy = ServiceOrderService.duplicate_order(
            db,
            order,
            org_id=principal.org_id,
            user_id=principal.user_id,
        )
        return {"ok": True, "order": ServiceOrderService.order_to_dict(copy)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{order_id}/pause")
def pause_order(order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        order = ServiceOrderService.pause_order(db, order)
        return ServiceOrderService.order_to_dict(order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{order_id}/resume")
def resume_order(order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        order = ServiceOrderService.resume_order(db, order)
        return ServiceOrderService.order_to_dict(order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{order_id}/stop")
def stop_order(order_id: str, payload: dict | None = None, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        order = ServiceOrderService.stop_order(db, order, reason=str((payload or {}).get("reason") or ""))
        return ServiceOrderService.order_to_dict(order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{order_id}/complete")
def complete_order(order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        order = ServiceOrderService.complete_order(db, order)
        return ServiceOrderService.order_to_dict(order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{order_id}/schedule")
def schedule_order(order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        order = ServiceOrderService.schedule_order(db, order)
        return ServiceOrderService.order_to_dict(order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{order_id}/start")
def start_order(order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        order = ServiceOrderService.start_order(db, order)
        return ServiceOrderService.order_to_dict(order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/scheduling/status")
def get_scheduling_status(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.scheduling_connection_service import scheduling_status

    return scheduling_status(db, principal.org_id)


@router.post("/scheduling/disconnect")
def disconnect_scheduling_account(
    body: dict | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.scheduling_connection_service import disconnect_scheduling

    provider = None
    if isinstance(body, dict):
        provider = body.get("provider")
    try:
        return disconnect_scheduling(db, principal.org_id, provider=str(provider).strip() if provider else None)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/scheduling/oauth/calendly/start")
def start_calendly_oauth(
    replace: bool = False,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.scheduling_connection_service import calendly_oauth_start

    try:
        return {"authorize_url": calendly_oauth_start(org_id=principal.org_id, db=db, replace=replace)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/scheduling/oauth/calendly/callback")
def calendly_oauth_callback(
    code: str = "",
    state: str = "",
    db: Session = Depends(get_db),
):
    from app.core.config import get_settings
    from app.services.scheduling_connection_service import calendly_oauth_complete

    calendly_oauth_complete(db, code=code, state=state)
    origin = str(get_settings().dashboard_app_origin or "http://localhost:5175").rstrip("/")
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url=f"{origin}/settings/integrations?scheduling=connected&provider=calendly")


@router.get("/scheduling/oauth/cal-com/start")
def start_cal_com_oauth(
    replace: bool = False,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.cal_com_connection_service import cal_com_oauth_start

    try:
        return {"authorize_url": cal_com_oauth_start(org_id=principal.org_id, db=db, replace=replace)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/scheduling/oauth/cal-com/callback")
def cal_com_oauth_callback(
    code: str = "",
    state: str = "",
    db: Session = Depends(get_db),
):
    from app.core.config import get_settings
    from app.services.cal_com_connection_service import cal_com_oauth_complete
    from fastapi.responses import RedirectResponse

    origin = str(get_settings().dashboard_app_origin or "http://localhost:5175").rstrip("/")
    try:
        cal_com_oauth_complete(db, code=code, state=state)
    except ValueError as exc:
        from urllib.parse import quote

        return RedirectResponse(
            url=f"{origin}/settings/integrations?scheduling=error&provider=cal_com&message={quote(str(exc)[:200])}"
        )
    return RedirectResponse(url=f"{origin}/settings/integrations?scheduling=connected&provider=cal_com")


@router.get("/scheduling/oauth/google-calendar/start")
def start_google_calendar_oauth(
    replace: bool = False,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.google_calendar_booking_service import google_calendar_oauth_start

    try:
        return {"authorize_url": google_calendar_oauth_start(org_id=principal.org_id, db=db, replace=replace)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/scheduling/oauth/google-calendar/callback")
def google_calendar_oauth_callback(
    code: str = "",
    state: str = "",
    db: Session = Depends(get_db),
):
    from urllib.parse import quote

    from app.core.config import get_settings
    from app.services.google_calendar_booking_service import google_calendar_oauth_complete
    from fastapi.responses import RedirectResponse

    origin = str(get_settings().dashboard_app_origin or "http://localhost:5175").rstrip("/")
    try:
        result = google_calendar_oauth_complete(db, code=code, state=state)
        if not result.get("google_calendar_connected"):
            msg = (
                "Google OAuth finished but the connection was not saved correctly. "
                "Verify ENCRYPTION_KEY on the API server, then reconnect."
            )
            return RedirectResponse(
                url=f"{origin}/settings/integrations?scheduling=error&provider=google_calendar&message={quote(msg)}"
            )
    except ValueError as exc:
        return RedirectResponse(
            url=f"{origin}/settings/integrations?scheduling=error&provider=google_calendar&message={quote(str(exc)[:200])}"
        )
    return RedirectResponse(url=f"{origin}/settings/integrations?scheduling=connected&provider=google_calendar")


@router.get("/scheduling/oauth/microsoft-calendar/start")
def start_microsoft_calendar_oauth(
    replace: bool = False,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.microsoft_calendar_service import microsoft_calendar_oauth_start

    try:
        return {
            "authorize_url": microsoft_calendar_oauth_start(
                org_id=principal.org_id, db=db, replace=replace
            )
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/scheduling/oauth/microsoft-calendar/callback")
def microsoft_calendar_oauth_callback(
    code: str = "",
    state: str = "",
    db: Session = Depends(get_db),
):
    import logging
    from urllib.parse import quote

    from app.core.config import get_settings
    from app.services.microsoft_calendar_service import microsoft_calendar_oauth_complete
    from fastapi.responses import RedirectResponse

    logger = logging.getLogger(__name__)
    origin = str(get_settings().dashboard_app_origin or "http://localhost:5175").rstrip("/")
    org_id = str(state).split(":", 1)[0].strip() if state else ""
    try:
        result = microsoft_calendar_oauth_complete(db, code=code, state=state)
        logger.info(
            "Microsoft Calendar OAuth saved org_id=%s connected=%s provider=%s",
            org_id,
            bool(result.get("microsoft_calendar_connected")),
            result.get("provider"),
        )
        if not result.get("microsoft_calendar_connected"):
            msg = (
                "Microsoft OAuth finished but the connection was not saved correctly. "
                "Verify ENCRYPTION_KEY on the API server, then reconnect."
            )
            return RedirectResponse(
                url=f"{origin}/settings/integrations?scheduling=error&provider=microsoft_calendar&message={quote(msg)}"
            )
    except ValueError as exc:
        logger.warning("Microsoft Calendar OAuth failed org_id=%s error=%s", org_id, str(exc)[:200])
        return RedirectResponse(
            url=f"{origin}/settings/integrations?scheduling=error&provider=microsoft_calendar&message={quote(str(exc)[:200])}"
        )
    return RedirectResponse(
        url=f"{origin}/settings/integrations?scheduling=connected&provider=microsoft_calendar"
    )


@router.get("/scheduling/microsoft-calendar/calendars")
def list_microsoft_calendar_calendars_route(
    db: Session = Depends(get_db), principal=Depends(get_current_principal)
):
    from app.services.microsoft_calendar_service import list_microsoft_calendar_calendars

    try:
        return {"calendars": list_microsoft_calendar_calendars(db, principal.org_id)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/scheduling/microsoft-calendar/select-schedule")
def select_microsoft_calendar_schedule_route(
    body: dict | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.microsoft_calendar_service import select_microsoft_calendar_schedule

    payload = body if isinstance(body, dict) else {}
    try:
        return select_microsoft_calendar_schedule(
            db,
            principal.org_id,
            schedule_url=str(payload.get("schedule_url") or ""),
            schedule_name=str(payload.get("schedule_name") or ""),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/scheduling/cal-com/event-types")
def list_cal_com_event_types_route(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.cal_com_connection_service import list_cal_com_event_types

    try:
        return {"event_types": list_cal_com_event_types(db, principal.org_id)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/scheduling/cal-com/select-event-type")
def select_cal_com_event_type_route(
    body: dict | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.cal_com_connection_service import select_cal_com_event_type

    event_type_id = str((body or {}).get("event_type_id") or "").strip()
    try:
        return select_cal_com_event_type(db, principal.org_id, event_type_id=event_type_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/scheduling/google-calendar/schedules")
def list_google_calendar_schedules_route(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.google_calendar_booking_service import list_google_calendar_schedules

    try:
        return {"schedules": list_google_calendar_schedules(db, principal.org_id)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/scheduling/google-calendar/select-schedule")
def select_google_calendar_schedule_route(
    body: dict | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.google_calendar_booking_service import select_google_calendar_schedule

    payload = body if isinstance(body, dict) else {}
    try:
        return select_google_calendar_schedule(
            db,
            principal.org_id,
            schedule_url=str(payload.get("schedule_url") or ""),
            schedule_name=str(payload.get("schedule_name") or ""),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/scheduling/hubspot/meeting-links")
def list_hubspot_meeting_links_route(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.hubspot_meetings_service import list_hubspot_meeting_links

    try:
        return {"meeting_links": list_hubspot_meeting_links(db, principal.org_id)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/scheduling/hubspot/select-meeting-link")
def select_hubspot_meeting_link_route(
    body: dict | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.hubspot_meetings_service import connect_hubspot_meetings

    payload = body if isinstance(body, dict) else {}
    try:
        return connect_hubspot_meetings(
            db,
            principal.org_id,
            meeting_link_id=str(payload.get("meeting_link_id") or ""),
            meeting_link_url=str(payload.get("meeting_link_url") or ""),
            meeting_link_name=str(payload.get("meeting_link_name") or ""),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/scheduling/zoho/booking-services")
def list_zoho_booking_services_route(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.zoho_bookings_service import list_zoho_booking_services

    try:
        return {"booking_services": list_zoho_booking_services(db, principal.org_id)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/scheduling/zoho/select-booking-service")
def select_zoho_booking_service_route(
    body: dict | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.zoho_bookings_service import connect_zoho_bookings

    payload = body if isinstance(body, dict) else {}
    try:
        return connect_zoho_bookings(
            db,
            principal.org_id,
            service_id=str(payload.get("service_id") or ""),
            service_url=str(payload.get("service_url") or ""),
            service_name=str(payload.get("service_name") or ""),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/scheduling/oauth/cronofy/start")
def start_cronofy_oauth_deprecated(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Cronofy is no longer supported. Connect Calendly, Cal.com, Google Calendar, or HubSpot Meetings instead.",
    )


@router.get("/scheduling/oauth/cronofy/callback")
def cronofy_oauth_callback_deprecated(
    db: Session = Depends(get_db),
):
    from app.core.config import get_settings
    from fastapi.responses import RedirectResponse

    origin = str(get_settings().dashboard_app_origin or "http://localhost:5175").rstrip("/")
    return RedirectResponse(
        url=f"{origin}/settings/integrations?scheduling=error&provider=cronofy&message=Cronofy+is+no+longer+supported"
    )


@router.get("/hubspot/status")
def get_hubspot_status(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.hubspot_connection_service import hubspot_status

    return hubspot_status(db, principal.org_id)


@router.patch("/hubspot/settings")
def patch_hubspot_settings(
    body: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.hubspot_connection_service import update_hubspot_settings

    try:
        return update_hubspot_settings(
            db,
            principal.org_id,
            auto_sync_shortlist=body.get("auto_sync_shortlist"),
            auto_sync_scheduling_send=body.get("auto_sync_scheduling_send"),
            create_task_on_unhappy_score=body.get("create_task_on_unhappy_score"),
            appointment_list_id=body.get("appointment_list_id"),
            survey_list_id=body.get("survey_list_id"),
            appointment_confirmed_list_id=body.get("appointment_confirmed_list_id"),
            appointment_cancelled_list_id=body.get("appointment_cancelled_list_id"),
            field_map=body.get("field_map") if isinstance(body.get("field_map"), dict) else None,
            auto_sync_results_back=body.get("auto_sync_results_back"),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/hubspot/lists")
def get_hubspot_lists(
    query: str = Query("", max_length=200),
    limit: int = Query(100, ge=1, le=250),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.crm_contact_sync_service import CrmContactSyncError, list_hubspot_lists_for_org

    try:
        return list_hubspot_lists_for_org(db, principal.org_id, query=query, limit=limit)
    except CrmContactSyncError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/hubspot/disconnect")
def disconnect_hubspot_account(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.hubspot_connection_service import disconnect_hubspot

    try:
        return disconnect_hubspot(db, principal.org_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/hubspot/connect-token")
def connect_hubspot_token(
    body: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.hubspot_connection_service import connect_hubspot_access_token

    token = str(body.get("access_token") or "").strip()
    try:
        return connect_hubspot_access_token(db, principal.org_id, token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/hubspot/oauth/start")
def start_hubspot_oauth(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.hubspot_connection_service import hubspot_oauth_start

    try:
        return {"authorize_url": hubspot_oauth_start(org_id=principal.org_id, db=db)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/hubspot/oauth/callback")
def hubspot_oauth_callback(
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
    db: Session = Depends(get_db),
):
    from urllib.parse import quote

    from app.core.config import get_settings
    from app.services.hubspot_connection_service import hubspot_oauth_complete

    origin = str(get_settings().dashboard_app_origin or "http://localhost:5175").rstrip("/")
    from fastapi.responses import RedirectResponse

    if error:
        msg = str(error_description or error).strip() or "HubSpot authorization was denied"
        return RedirectResponse(
            url=f"{origin}/settings/integrations?hubspot=error&message={quote(msg[:200])}"
        )
    try:
        hubspot_oauth_complete(db, code=code, state=state)
    except ValueError as exc:
        return RedirectResponse(url=f"{origin}/settings/integrations?hubspot=error&message={quote(str(exc)[:200])}")
    return RedirectResponse(url=f"{origin}/settings/integrations?hubspot=connected")


@router.get("/pipedrive/status")
def get_pipedrive_status(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.pipedrive_connection_service import pipedrive_status

    return pipedrive_status(db, principal.org_id)


@router.patch("/pipedrive/settings")
def patch_pipedrive_settings(
    body: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.pipedrive_connection_service import update_pipedrive_settings

    try:
        return update_pipedrive_settings(
            db,
            principal.org_id,
            auto_sync_shortlist=body.get("auto_sync_shortlist"),
            auto_sync_scheduling_send=body.get("auto_sync_scheduling_send"),
            create_task_on_unhappy_score=body.get("create_task_on_unhappy_score"),
            auto_sync_results_back=body.get("auto_sync_results_back"),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/crm/sync-status")
def get_crm_sync_status(
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.crm_contact_sync_service import crm_sync_status

    return crm_sync_status(db, principal.org_id)


@router.post("/crm/contacts/sync")
def sync_crm_contacts(
    body: dict | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.crm_contact_sync_service import CrmContactSyncError, sync_contacts

    payload = body or {}
    try:
        limit = int(payload.get("limit") or 100)
    except (TypeError, ValueError):
        limit = 100
    try:
        return sync_contacts(db, principal.org_id, limit=limit)
    except CrmContactSyncError as exc:
        msg = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not enabled" in msg.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=msg) from exc


@router.get("/crm/contacts")
def list_crm_contacts(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.crm_contact_sync_service import CrmContactSyncError, list_contacts

    try:
        return list_contacts(db, principal.org_id, limit=limit)
    except CrmContactSyncError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/crm/contacts/import-to-order")
def import_crm_contacts_to_order(
    body: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.crm_contact_sync_service import CrmContactSyncError, import_contacts_to_order

    order_id = str(body.get("order_id") or "").strip()
    contact_ids = body.get("contact_ids") or []
    if not order_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="order_id required")
    try:
        return import_contacts_to_order(
            db,
            principal.org_id,
            order_id=order_id,
            contact_ids=list(contact_ids),
        )
    except CrmContactSyncError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/crm/sync-settings")
def patch_crm_sync_settings(
    body: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.crm_contact_sync_service import CrmContactSyncError, update_crm_sync_settings

    field_map = body.get("field_map")
    if field_map is not None and not isinstance(field_map, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="field_map must be an object")
    try:
        return update_crm_sync_settings(
            db,
            principal.org_id,
            field_map=field_map,
            auto_sync_results_back=body.get("auto_sync_results_back"),
            appointment_list_id=body.get("appointment_list_id"),
            survey_list_id=body.get("survey_list_id"),
            appointment_confirmed_list_id=body.get("appointment_confirmed_list_id"),
            appointment_cancelled_list_id=body.get("appointment_cancelled_list_id"),
        )
    except CrmContactSyncError as exc:
        msg = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not enabled" in msg.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=msg) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/crm/lists/import-to-order")
def import_crm_list_to_order(
    body: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.crm_contact_sync_service import CrmContactSyncError, import_list_contacts_to_order

    order_id = str(body.get("order_id") or "").strip()
    list_id = str(body.get("list_id") or "").strip() or None
    if not order_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="order_id required")
    try:
        return import_list_contacts_to_order(
            db,
            principal.org_id,
            order_id=order_id,
            list_id=list_id,
        )
    except CrmContactSyncError as exc:
        msg = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not enabled" in msg.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=msg) from exc


@router.post("/{order_id}/recipients/{recipient_id}/crm/sync-result")
def push_survey_result_to_crm(
    order_id: str,
    recipient_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.crm_survey_result_sync_service import sync_survey_result_to_active_crm

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.service_code != "survey":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CRM result sync is only supported for surveys")

    recipient = ServiceOrderService.get_recipient(db, order.id, recipient_id)
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    if str(recipient.status or "").lower() != "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only completed survey responses can be pushed to CRM")

    try:
        result = sync_survey_result_to_active_crm(
            db,
            principal.org_id,
            order=order,
            recipient=recipient,
            force=True,
        )
        db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/crm/deal-stages")
def list_crm_deal_stages_route(
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.crm_deal_survey_automation_service import CrmDealSurveyAutomationError, list_crm_deal_stages

    try:
        return {"stages": list_crm_deal_stages(db, principal.org_id)}
    except CrmDealSurveyAutomationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{order_id}/crm-automation")
def get_crm_survey_automation(
    order_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.crm_deal_survey_automation_service import automation_status

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.service_code != "survey":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CRM automation is only supported for surveys")
    return automation_status(db, principal.org_id, order)


@router.patch("/{order_id}/crm-automation")
def patch_crm_survey_automation(
    order_id: str,
    body: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.crm_deal_survey_automation_service import (
        CrmDealSurveyAutomationError,
        update_crm_automation_settings,
    )

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        stage_ids = body.get("stage_ids")
        return update_crm_automation_settings(
            db,
            principal.org_id,
            order=order,
            enabled=body.get("enabled"),
            stage_ids=list(stage_ids) if isinstance(stage_ids, list) else None,
            delay_hours=body.get("delay_hours"),
            consent_acknowledged=body.get("consent_acknowledged"),
        )
    except CrmDealSurveyAutomationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{order_id}/crm-automation/test")
def test_crm_survey_automation(
    order_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.crm_deal_survey_automation_service import CrmDealSurveyAutomationError, dry_run_crm_automation

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        return dry_run_crm_automation(db, principal.org_id, order)
    except CrmDealSurveyAutomationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/pipedrive/oauth/start")
def start_pipedrive_oauth(
    replace: bool = False,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.pipedrive_connection_service import pipedrive_oauth_start

    try:
        return {"authorize_url": pipedrive_oauth_start(org_id=principal.org_id, db=db, replace=replace)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/pipedrive/oauth/callback")
def pipedrive_oauth_callback(
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
    replace: bool = False,
    db: Session = Depends(get_db),
):
    from urllib.parse import quote

    from app.core.config import get_settings
    from app.services.pipedrive_connection_service import pipedrive_oauth_complete
    from fastapi.responses import RedirectResponse

    origin = str(get_settings().dashboard_app_origin or "http://localhost:5175").rstrip("/")
    if error:
        msg = str(error_description or error).strip() or "Pipedrive authorization was denied"
        return RedirectResponse(
            url=f"{origin}/settings/integrations?crm=error&provider=pipedrive&message={quote(msg[:200])}"
        )
    try:
        pipedrive_oauth_complete(db, code=code, state=state, replace=replace)
    except ValueError as exc:
        return RedirectResponse(
            url=f"{origin}/settings/integrations?crm=error&provider=pipedrive&message={quote(str(exc)[:200])}"
        )
    return RedirectResponse(
        url=f"{origin}/settings/integrations?crm=connected&provider=pipedrive&tab=crm"
    )


@router.get("/zoho-crm/status")
def get_zoho_crm_status(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.zoho_crm_connection_service import zoho_crm_status

    return zoho_crm_status(db, principal.org_id)


@router.patch("/zoho-crm/settings")
def patch_zoho_crm_settings(
    body: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.zoho_crm_connection_service import update_zoho_crm_settings

    try:
        return update_zoho_crm_settings(
            db,
            principal.org_id,
            auto_sync_shortlist=body.get("auto_sync_shortlist"),
            auto_sync_scheduling_send=body.get("auto_sync_scheduling_send"),
            create_task_on_unhappy_score=body.get("create_task_on_unhappy_score"),
            auto_sync_results_back=body.get("auto_sync_results_back"),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/zoho-crm/oauth/start")
def start_zoho_crm_oauth(
    replace: bool = False,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.zoho_crm_connection_service import zoho_crm_oauth_start

    try:
        return {"authorize_url": zoho_crm_oauth_start(org_id=principal.org_id, db=db, replace=replace)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/zoho-crm/oauth/callback")
def zoho_crm_oauth_callback(
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
    replace: bool = False,
    db: Session = Depends(get_db),
):
    from urllib.parse import quote

    from app.core.config import get_settings
    from app.services.zoho_crm_connection_service import zoho_crm_oauth_complete
    from fastapi.responses import RedirectResponse

    origin = str(get_settings().dashboard_app_origin or "http://localhost:5175").rstrip("/")
    if error:
        msg = str(error_description or error).strip() or "Zoho authorization was denied"
        return RedirectResponse(
            url=f"{origin}/settings/integrations?crm=error&provider=zoho_crm&message={quote(msg[:200])}"
        )
    try:
        zoho_crm_oauth_complete(db, code=code, state=state, replace=replace)
    except ValueError as exc:
        return RedirectResponse(
            url=f"{origin}/settings/integrations?crm=error&provider=zoho_crm&message={quote(str(exc)[:200])}"
        )
    return RedirectResponse(
        url=f"{origin}/settings/integrations?crm=connected&provider=zoho_crm&tab=crm"
    )


@router.get("/{order_id}/interview/ats/quote")
def quote_interview_ats(
    order_id: str,
    force: bool = False,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    import logging

    from app.services.interview_ats_billing_service import InterviewAtsBillingError, quote_ats_run

    logger = logging.getLogger(__name__)
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        return quote_ats_run(db, order, force=force)
    except InterviewAtsBillingError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.exception("quote_interview_ats_failed order_id=%s", order_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not calculate ATS pricing. If this persists, contact support — the server may need a database update.",
        ) from e


@router.post("/{order_id}/interview/ats/run")
def run_interview_ats(
    order_id: str,
    background_tasks: BackgroundTasks,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.interview_ats_billing_service import (
        InterviewAtsBillingError,
        background_process_ats_scans,
        charge_and_queue_ats,
    )
    from app.services.recovery_service import OrganisationService

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    org = OrganisationService.get_org(db, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    body = payload or {}
    try:
        result = charge_and_queue_ats(
            db,
            order,
            org,
            confirm_charge=bool(body.get("confirm_charge")),
            force=bool(body.get("force")),
            process_inline=False,
        )
        queued = int(result.get("queued") or 0)
        if queued > 0:
            background_tasks.add_task(background_process_ats_scans, limit=max(1, min(queued, 8)))
        return result
    except InterviewAtsBillingError as e:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(e)) from e


@router.post("/{order_id}/interview/ats/apply-threshold")
def apply_interview_ats_threshold(
    order_id: str,
    payload: dict = Body(default_factory=dict),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.interview_cv_exclusion_service import apply_ats_threshold_to_order
    from app.services.interview_cv_collection_service import CvCollectionConfigError, validate_and_apply_cv_config
    from app.services.interview_cv_email_service import _loads_config

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    body = payload if isinstance(payload, dict) else {}
    raw_min = body.get("min_ats_score")
    if raw_min is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="min_ats_score is required")
    try:
        min_score = max(0, min(100, int(raw_min)))
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid min_ats_score") from e
    previous = _loads_config(order)
    if previous.get("cv_email_enabled"):
        try:
            validate_and_apply_cv_config(
                db,
                principal.org_id,
                order,
                {"cv_min_ats_score": min_score},
                previous_cfg=previous,
            )
        except CvCollectionConfigError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    try:
        result = apply_ats_threshold_to_order(db, order, min_score=min_score)
        db.refresh(order)
        result["order"] = ServiceOrderService.order_to_dict(order)
        return result
    except Exception as e:
        import logging

        logging.getLogger(__name__).exception("apply_interview_ats_threshold_failed order_id=%s", order_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not apply ATS cutoff to candidates.",
        ) from e


@router.post("/{order_id}/interview/cv-collection/close-early")
def close_interview_cv_collection_early(
    order_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.interview_cv_email_service import close_cv_collection_early

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        payload = close_cv_collection_early(db, order)
        db.refresh(order)
        from app.services.interview_intake_service import intake_summary, list_intake_recipients

        recipients = list_intake_recipients(db, order)
        payload["order"] = ServiceOrderService.order_to_dict(order)
        payload["recipients"] = recipients
        payload["summary"] = intake_summary(recipients)
        return payload
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/hubspot/contacts/sync")
def sync_hubspot_contacts(
    body: dict | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.hubspot_contact_sync_service import HubspotContactSyncError, fetch_and_upsert_contacts

    payload = body or {}
    try:
        limit = int(payload.get("limit") or 100)
    except (TypeError, ValueError):
        limit = 100
    try:
        return fetch_and_upsert_contacts(db, principal.org_id, limit=limit)
    except HubspotContactSyncError as exc:
        msg = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not enabled" in msg.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=msg) from exc


@router.get("/hubspot/contacts")
def list_hubspot_contacts(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.hubspot_contact_sync_service import HubspotContactSyncError, list_contacts

    try:
        return list_contacts(db, principal.org_id, limit=limit)
    except HubspotContactSyncError as exc:
        msg = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not enabled" in msg.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=msg) from exc


@router.post("/hubspot/contacts/import-to-order")
def import_hubspot_contacts_to_order(
    body: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.hubspot_contact_sync_service import HubspotContactSyncError, import_contacts_to_order

    order_id = str(body.get("order_id") or "").strip()
    contact_ids = body.get("contact_ids") or []
    if not order_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="order_id required")
    try:
        return import_contacts_to_order(
            db,
            principal.org_id,
            order_id=order_id,
            contact_ids=list(contact_ids),
        )
    except HubspotContactSyncError as exc:
        msg = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not enabled" in msg.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=msg) from exc


@router.patch("/hubspot/sync-settings")
def patch_hubspot_sync_settings(
    body: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.hubspot_contact_sync_service import HubspotContactSyncError, update_hubspot_sync_settings

    field_map = body.get("field_map")
    if field_map is not None and not isinstance(field_map, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="field_map must be an object")
    try:
        return update_hubspot_sync_settings(
            db,
            principal.org_id,
            field_map=field_map,
            auto_sync_results_back=body.get("auto_sync_results_back"),
        )
    except HubspotContactSyncError as exc:
        msg = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not enabled" in msg.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=msg) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{order_id}/recipients/{recipient_id}/hubspot/sync-result")
def push_survey_result_to_hubspot(
    order_id: str,
    recipient_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.models.service_order import ServiceOrderRecipient
    from app.services.hubspot_contact_sync_service import HubspotContactSyncError, sync_survey_result_to_hubspot

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.service_code != "survey":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="HubSpot result sync is only supported for surveys")

    recipient = ServiceOrderService.get_recipient(db, order.id, recipient_id)
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    if str(recipient.status or "").lower() != "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only completed survey responses can be pushed to HubSpot")

    try:
        result = sync_survey_result_to_hubspot(db, principal.org_id, order=order, recipient=recipient, force=True)
        db.commit()
        return result
    except HubspotContactSyncError as exc:
        msg = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not enabled" in msg.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=msg) from exc


@router.patch("/{order_id}/interview-shortlist")
def save_interview_shortlist(
    order_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.interview_scheduling_service import InterviewSchedulingService

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        ids = payload.get("recipient_ids") or []
        return InterviewSchedulingService.save_shortlist(db, order, list(ids))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{order_id}/interview-scheduling/send")
def send_interview_scheduling(
    order_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.interview_scheduling_service import InterviewSchedulingService

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    body = payload or {}
    try:
        return InterviewSchedulingService.send_scheduling_links(
            db,
            order,
            recipient_ids=body.get("recipient_ids"),
            channels=body.get("channels"),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{order_id}/interview/launch")
def launch_interview_after_payment(
    order_id: str,
    payload: dict = Body(default_factory=dict),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    import logging

    from app.models.organisation import Organisation
    from app.services.interview_launch_service import InterviewLaunchService

    logger = logging.getLogger(__name__)
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    body = payload if isinstance(payload, dict) else {}
    try:
        launch_channels = body.get("channels")
        if not launch_channels:
            launch_channels = ["email", "whatsapp"]
        # Validate phones/emails before payment approval so a bad Excel row never bills then fails mid-send.
        InterviewLaunchService.assert_recipients_ready_for_launch(db, order, channels=launch_channels)
        if order.payment_status != "approved":
            from app.services.interview_launch_eligibility_service import (
                InterviewLaunchEligibilityError,
                InterviewLaunchEligibilityService,
            )

            try:
                order = InterviewLaunchEligibilityService.approve_if_covered(db, order, org)
            except InterviewLaunchEligibilityError as e:
                raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(e)) from e
        return InterviewLaunchService.launch_after_payment(
            db,
            order,
            resend_invites=bool(body.get("resend_invites") or body.get("force_resend")),
            channels=launch_channels,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.exception("interview_launch_failed order_id=%s org_id=%s", order_id, principal.org_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e) or "Could not launch interview campaign",
        ) from e


@router.get("/{order_id}/interview-booking/preview-template")
def preview_interview_booking_template(
    order_id: str,
    sync: bool = True,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.interview_booking_service import InterviewBookingService

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    preview = InterviewBookingService.preview_template(db, order, sync_first=sync)
    return {"template": preview}


@router.post("/{order_id}/interview-booking/send-invites")
def send_interview_booking_invites(
    order_id: str,
    payload: dict = Body(default_factory=dict),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.interview_booking_service import InterviewBookingService

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    body = payload if isinstance(payload, dict) else {}
    try:
        channels = body.get("channels")
        if not channels:
            channels = ["email", "whatsapp"]
        force_resend = bool(body.get("force_resend"))
        force_email = bool(body.get("force_email") or force_resend)
        return InterviewBookingService.send_invites(
            db,
            order,
            recipient_ids=body.get("recipient_ids"),
            channels=channels,
            force_resend=force_resend,
            force_email=force_email,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{order_id}/interview-results")
def get_interview_results(order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.interview_results_service import InterviewResultsService

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        return InterviewResultsService.get_results(db, order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{order_id}/recipients/{recipient_id}/interview-detail")
def get_interview_recipient_detail(
    order_id: str,
    recipient_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.models.service_order import ServiceOrderRecipient
    from app.services.interview_results_service import InterviewResultsService

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    recipient = db.get(ServiceOrderRecipient, recipient_id)
    if recipient is None or recipient.order_id != order.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    try:
        return InterviewResultsService.get_recipient_detail(db, order, recipient)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{order_id}/recipients/{recipient_id}/activity")
def get_interview_recipient_activity(
    order_id: str,
    recipient_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.models.service_order import ServiceOrderRecipient
    from app.services.interview_activity_service import InterviewActivityService

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    recipient = db.get(ServiceOrderRecipient, recipient_id)
    if recipient is None or recipient.order_id != order.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    return InterviewActivityService.timeline(db, order, recipient)


@router.get("/{order_id}/recipients/{recipient_id}/interview-candidate-report.html")
def get_interview_candidate_report_html(
    order_id: str,
    recipient_id: str,
    include_cv: bool = False,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.models.service_order import ServiceOrderRecipient
    from app.services.interview_candidate_report_export_service import InterviewCandidateReportExportService
    from fastapi.responses import HTMLResponse

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    recipient = db.get(ServiceOrderRecipient, recipient_id)
    if recipient is None or recipient.order_id != order.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    html_doc = InterviewCandidateReportExportService.html(db, order, recipient, include_cv=include_cv)
    return HTMLResponse(content=html_doc)


@router.get("/{order_id}/recipients/{recipient_id}/interview-candidate-report.pdf")
def get_interview_candidate_report_pdf(
    order_id: str,
    recipient_id: str,
    include_cv: bool = False,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.models.service_order import ServiceOrderRecipient
    from app.services.interview_candidate_report_export_service import InterviewCandidateReportExportService
    from fastapi.responses import Response

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    recipient = db.get(ServiceOrderRecipient, recipient_id)
    if recipient is None or recipient.order_id != order.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    pdf_bytes = InterviewCandidateReportExportService.pdf(db, order, recipient, include_cv=include_cv)
    name = (recipient.name or "candidate").replace(" ", "-").lower()[:40]
    suffix = "-with-cv" if include_cv else ""
    filename = f"interview-report-{name}{suffix}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/{order_id}/recipients/{recipient_id}/recording")
def get_interview_recipient_recording(
    order_id: str,
    recipient_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from fastapi.responses import RedirectResponse, Response

    from app.models.service_order import ServiceOrderRecipient
    from app.services.interview_recording_service import (
        USER_RECORDING_PROCESSING,
        USER_RECORDING_UNAVAILABLE,
        fetch_interview_recording,
    )

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    recipient = db.get(ServiceOrderRecipient, recipient_id)
    if recipient is None or recipient.order_id != order.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")

    try:
        parsed = json.loads(recipient.result_json or "{}")
        if not isinstance(parsed, dict):
            parsed = {}
    except Exception:
        parsed = {}

    remote = str(parsed.get("recording_url") or "").strip()
    if remote.startswith("http://") or remote.startswith("https://"):
        return RedirectResponse(url=remote, status_code=302)

    try:
        result = fetch_interview_recording(db, recipient)
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "interview_recording_fetch_failed order_id=%s recipient_id=%s",
            order.id,
            recipient.id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=USER_RECORDING_UNAVAILABLE,
        ) from None

    if result:
        content, media_type = result
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": 'inline; filename="interview-recording.mp3"'},
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=USER_RECORDING_PROCESSING,
    )


@router.get("/{order_id}/interview-results/export.csv")
def export_interview_results_csv(
    order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)
):
    from app.services.interview_results_service import InterviewResultsService
    from fastapi.responses import Response

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    csv_text = InterviewResultsService.export_results_csv(db, order)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="interview-results-{order_id[:8]}.csv"'},
    )


@router.get("/{order_id}/interview-results/export.pdf")
def export_interview_results_pdf(
    order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)
):
    from app.services.interview_results_service import InterviewResultsService
    from fastapi.responses import Response

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    pdf_bytes = InterviewResultsService.export_results_pdf(db, order)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="interview-results-{order_id[:8]}.pdf"'},
    )


@router.get("/{order_id}/interview-report")
def get_interview_batch_report(order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.interview_report_service import InterviewReportService

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        return InterviewReportService.batch_detail(db, order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{order_id}/interview-report/export.csv")
def export_interview_batch_report_csv(
    order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)
):
    from app.services.interview_report_service import InterviewReportService
    from fastapi.responses import Response

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        detail = InterviewReportService.batch_detail(db, order)
        csv_text = InterviewReportService.export_batch_csv(detail)
        ref = str((detail.get("summary") or {}).get("reference_id") or order_id[:8])
        filename = f"interview-report-{ref}.csv"
        return Response(
            content=csv_text,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{order_id}/survey-voice-notes/{job_id}/audio")
def download_survey_voice_note_audio(
    order_id: str,
    job_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from pathlib import Path

    from fastapi.responses import FileResponse

    from app.models.survey_voice_note_job import SurveyVoiceNoteJob
    from app.services.survey_analysis_service import _recipient_result

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    job = db.get(SurveyVoiceNoteJob, job_id)
    if job is None or not job.audio_file_path or job.audio_deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice note audio not found")

    allowed = False
    if str(job.order_id or "") == order_id:
        allowed = True
    else:
        recipients = ServiceOrderService.get_recipients(db, order_id)
        for recipient in recipients:
            result = _recipient_result(recipient)
            wa_conv = result.get("wa_conversation") if isinstance(result.get("wa_conversation"), dict) else {}
            for ans in wa_conv.get("answers") or []:
                if isinstance(ans, dict) and str(ans.get("voice_note_job_id") or "") == job_id:
                    allowed = True
                    break
            if allowed:
                break
    if not allowed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice note audio not found")

    path = Path(str(job.audio_file_path))
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice note audio file missing")
    media_type = str(job.audio_mime_type or "audio/ogg")
    return FileResponse(path, media_type=media_type, filename=path.name)


@router.get("/{order_id}/survey-results")
def get_survey_results(order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.survey_results_service import SurveyResultsService
    import json

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        config = json.loads(order.config_json or "{}")
    except Exception:
        config = {}
    hide_names = bool(config.get("anonymous_responses"))
    try:
        payload = SurveyResultsService.get_results(db, order, anonymous=hide_names)
        payload["anonymous_responses"] = hide_names
        payload["allow_follow_up"] = not hide_names
        return payload
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{order_id}/survey-results/export.csv")
def export_survey_results_csv(order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.survey_results_service import SurveyResultsService
    from fastapi.responses import Response

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        csv_text = SurveyResultsService.export_results_csv(db, order)
        filename = f"survey-results-{order_id[:8]}.csv"
        return Response(
            content=csv_text,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{order_id}/survey-results/export.pdf")
def export_survey_results_pdf(order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.survey_results_service import SurveyResultsService
    from fastapi.responses import Response

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        pdf_bytes = SurveyResultsService.export_results_pdf(db, order)
        filename = f"survey-results-{order_id[:8]}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{order_id}/survey-results/export.xlsx")
def export_survey_results_xlsx(order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.survey_results_service import SurveyResultsService
    from fastapi.responses import Response

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        xlsx_bytes = SurveyResultsService.export_results_xlsx(db, order)
        filename = f"survey-results-{order_id[:8]}.xlsx"
        return Response(
            content=xlsx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e


@router.get("/{order_id}/recipients/{recipient_id}/survey-detail")
def get_survey_recipient_detail(
    order_id: str,
    recipient_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.models.service_order import ServiceOrderRecipient
    from app.services.survey_results_service import SurveyResultsService

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Individual call transcripts are not available on the customer dashboard. View anonymous aggregate results instead.",
    )
