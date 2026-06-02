from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrderRecipient
from app.services.org_service_credit_service import OrgServiceCreditError, OrgServiceCreditService
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService
from app.services.gocardless_service import BillingService, GoCardlessConfigError, GoCardlessProviderError

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
        _, _, visible = org_service_maps(org)
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
    out = []
    for svc in services:
        if svc.code == "survey":
            survey_catalog = PlatformCatalogService.survey_packages_for_service(db, svc, active_only=True)
            out.append(
                {
                    "id": svc.id,
                    "code": svc.code,
                    "name": svc.name,
                    "description": svc.description,
                    "service_kind": svc.service_kind,
                    "setup_fee_pence": survey_catalog["setup_fee_pence"],
                    "setup_fee_gbp": survey_catalog["setup_fee_gbp"],
                    "packages": survey_catalog["packages"],
                }
            )
            continue

        rules = PlatformCatalogService.list_rules_for_service(db, svc.id)
        out.append(
            {
                "id": svc.id,
                "code": svc.code,
                "name": svc.name,
                "description": svc.description,
                "service_kind": svc.service_kind,
                "pricing_rules": [PlatformCatalogService.rule_to_dict(r) for r in rules],
            }
        )
    return out


@router.get("/survey-packages")
def list_survey_packages(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_org_service(db, principal.org_id, "survey")
    svc = PlatformCatalogService.get_service_by_code(db, "survey")
    if svc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey service not found")
    return PlatformCatalogService.survey_packages_for_service(db, svc, active_only=True)


@router.get("/credits")
def get_promo_credits(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    return {"ok": True, **OrgServiceCreditService.balances_dict(org)}


@router.get("/template.csv")
def download_recipient_template(_principal=Depends(get_current_principal)):
    return PlainTextResponse(
        ServiceOrderService.recipient_template_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="voxbulk-contacts-template.csv"'},
    )


@router.post("/quote")
def quote_preview(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    service_code = str(payload.get("service_code") or "")
    _require_org_service(db, principal.org_id, service_code)
    try:
        return PlatformCatalogService.calculate_quote(
            db,
            service_code=str(payload.get("service_code") or ""),
            recipient_count=int(payload.get("recipient_count") or 0),
            options=payload.get("options") or {},
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
        options: dict = {}
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
        return [ServiceOrderService.order_to_dict(r) for r in visible]


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
        return ServiceOrderService.order_to_dict(order)
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


@router.get("/interview/billing-context")
def get_interview_billing_context(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.interview_billing_context import org_interview_billing_context

    org = _require_org_service(db, principal.org_id, "interview")
    return org_interview_billing_context(db, org)


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
    from app.services.interview_intake_service import create_new_interview_draft, intake_summary
    from app.services.interview_billing_context import org_interview_billing_context

    org = _require_org_service(db, principal.org_id, "interview")
    order = create_new_interview_draft(db, org_id=principal.org_id, user_id=principal.user_id)
    billing = org_interview_billing_context(db, org)
    return _interview_draft_payload(db, order=order, recipients=[], summary=intake_summary([]), billing=billing)


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
        order = ServiceOrderService.update_order(db, order, {"config": config_patch})
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


@router.get("/gocardless/browser-return")
def gocardless_order_browser_return(
    session_token: str,
    order_billing: str = "success",
    db: Session = Depends(get_db),
):
    """GoCardless order payment return hop — sends browser to dashboard with order_billing params."""
    from fastapi.responses import RedirectResponse

    target = BillingService.complete_order_browser_return(
        db,
        session_token=session_token,
        order_billing=order_billing,
    )
    return RedirectResponse(url=target, status_code=302)


@router.post("/gocardless/complete")
def complete_gocardless_order_payment(
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    redirect_flow_id = str((payload or {}).get("redirect_flow_id") or "").strip()
    if not redirect_flow_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="redirect_flow_id required")
    try:
        res = BillingService.complete_service_order_gocardless_flow(
            db,
            org_id=principal.org_id,
            user_id=principal.user_id,
            redirect_flow_id=redirect_flow_id,
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except GoCardlessConfigError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except GoCardlessProviderError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e


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
    return ServiceOrderService.order_to_dict(order, include_recipients=True, recipients=recipients)


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
        order = ServiceOrderService.update_order(db, order, payload)
        return ServiceOrderService.order_to_dict(order)
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
            raise ValueError("No valid contacts found in file")
        order = ServiceOrderService.replace_recipients(db, order, rows)
        order = ServiceOrderService.quote_order(db, order)
        return ServiceOrderService.order_to_dict(order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{order_id}/quote")
def refresh_quote(order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    import logging

    from app.models.organisation import Organisation
    from app.services.interview_billing_context import org_interview_billing_context
    from app.services.pricing_market_service import PricingMarketService

    logger = logging.getLogger(__name__)
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    org = db.get(Organisation, principal.org_id)
    try:
        billing = org_interview_billing_context(db, org) if org else {}
        if order.service_code == "interview" and billing.get("has_active_subscription"):
            payload = ServiceOrderService.order_to_dict(order)
            plan_name = str(billing.get("plan_name") or "your package").strip() or "your package"
            payload["quote_total_pence"] = 0
            payload["quote_total_display"] = f"Included in {plan_name}"
            payload["pricing_market"] = PricingMarketService.market_for_org(db, org)
            payload["included_in_package"] = True
            return payload
        order = ServiceOrderService.quote_order(db, order)
        payload = ServiceOrderService.order_to_dict(order)
        return PricingMarketService.attach_order_quote_display(db, payload, org)
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


@router.post("/{order_id}/pay-cash")
def pay_cash(order_id: str, payload: dict | None = None, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        order = ServiceOrderService.submit_cash_payment(db, order, note=str((payload or {}).get("note") or ""))
        return ServiceOrderService.order_to_dict(order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{order_id}/gocardless/start")
def start_gocardless_order_payment(
    order_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    try:
        res = BillingService.start_service_order_gocardless_flow(
            db,
            org_id=principal.org_id,
            user_id=principal.user_id,
            order_id=order_id,
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except GoCardlessConfigError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except GoCardlessProviderError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e


@router.delete("/{order_id}")
def delete_order(order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        ServiceOrderService.delete_order(db, order)
        return {"ok": True}
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


@router.get("/scheduling/oauth/calendly/start")
def start_calendly_oauth(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.scheduling_connection_service import calendly_oauth_start

    try:
        return {"authorize_url": calendly_oauth_start(org_id=principal.org_id, db=db)}
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


@router.get("/scheduling/oauth/cronofy/start")
def start_cronofy_oauth(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.scheduling_connection_service import cronofy_oauth_start

    try:
        return {"authorize_url": cronofy_oauth_start(org_id=principal.org_id, db=db)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/scheduling/oauth/cronofy/callback")
def cronofy_oauth_callback(
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
    db: Session = Depends(get_db),
):
    from urllib.parse import quote

    from app.core.config import get_settings
    from app.services.scheduling_connection_service import cronofy_oauth_complete

    origin = str(get_settings().dashboard_app_origin or "http://localhost:5175").rstrip("/")
    from fastapi.responses import RedirectResponse

    if error:
        msg = str(error_description or error).strip() or "Cronofy authorization was denied"
        return RedirectResponse(
            url=f"{origin}/settings/integrations?scheduling=error&provider=cronofy&message={quote(msg[:200])}"
        )
    try:
        cronofy_oauth_complete(db, code=code, state=state)
    except ValueError as exc:
        return RedirectResponse(
            url=f"{origin}/settings/integrations?scheduling=error&provider=cronofy&message={quote(str(exc)[:200])}"
        )
    return RedirectResponse(url=f"{origin}/settings/integrations?scheduling=connected&provider=cronofy")


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
        )
    except ValueError as e:
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
    payload: dict | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.interview_ats_billing_service import InterviewAtsBillingError, charge_and_queue_ats
    from app.services.recovery_service import OrganisationService

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    org = OrganisationService.get_org(db, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    body = payload or {}
    try:
        return charge_and_queue_ats(
            db,
            order,
            org,
            confirm_charge=bool(body.get("confirm_charge")),
            force=bool(body.get("force")),
        )
    except InterviewAtsBillingError as e:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(e)) from e


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
        return close_cv_collection_early(db, order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


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
    payload: dict | None = None,
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
    body = payload or {}
    try:
        if order.payment_status != "approved":
            order = InterviewLaunchService.approve_for_subscription_package(db, order, org)
        return InterviewLaunchService.launch_after_payment(
            db,
            order,
            resend_invites=bool(body.get("resend_invites")),
            channels=body.get("channels"),
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
    payload: dict | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.interview_booking_service import InterviewBookingService

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    body = payload or {}
    try:
        return InterviewBookingService.send_invites(
            db,
            order,
            recipient_ids=body.get("recipient_ids"),
            channels=body.get("channels"),
            force_resend=bool(body.get("force_resend")),
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
    import httpx
    from fastapi.responses import RedirectResponse, Response

    from app.models.service_order import ServiceOrderRecipient

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

    # Telnyx recording download URL stored on completed calls
    download_url = str(parsed.get("telnyx_recording_download_url") or "").strip()
    if download_url.startswith("http"):
        try:
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                resp = client.get(download_url)
                resp.raise_for_status()
            media_type = resp.headers.get("content-type") or "audio/mpeg"
            return Response(
                content=resp.content,
                media_type=media_type,
                headers={"Content-Disposition": 'inline; filename="interview-recording.mp3"'},
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not fetch Telnyx recording: {exc}",
            ) from exc

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Recording not available yet. Telnyx may still be processing — try again in a minute.",
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


@router.get("/{order_id}/survey-results")
def get_survey_results(order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.survey_results_service import SurveyResultsService

    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        return SurveyResultsService.get_results(db, order, anonymous=True)
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
