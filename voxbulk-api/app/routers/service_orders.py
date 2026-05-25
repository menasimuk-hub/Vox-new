from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.models.organisation import Organisation
from app.services.org_service_credit_service import OrgServiceCreditError, OrgServiceCreditService
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService
from app.services.gocardless_service import BillingService, GoCardlessConfigError, GoCardlessProviderError

router = APIRouter(prefix="/service-orders", tags=["service-orders"])


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
def list_survey_packages(db: Session = Depends(get_db), _principal=Depends(get_current_principal)):
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
def quote_preview(payload: dict, db: Session = Depends(get_db), _principal=Depends(get_current_principal)):
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
    _principal=Depends(get_current_principal),
):
    content = await file.read()
    try:
        rows = ServiceOrderService.parse_recipient_file(content, file.filename or "upload.csv")
        if not rows:
            raise ValueError("No valid contacts found in file")
        code = str(service_code or "interview").strip().lower()
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
    rows = ServiceOrderService.list_orders(db, org_id=principal.org_id, service_code=service_code)
    return [ServiceOrderService.order_to_dict(r) for r in rows]


@router.post("")
def create_order(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
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
    from app.services.survey_voice_agent_service import list_dashboard_agents_for_service
    from app.core.agent_services import SERVICE_SURVEY

    return {
        "agents": list_dashboard_agents_for_service(db, service_key=SERVICE_SURVEY, org_id=principal.org_id),
    }


@router.get("/interview-agents")
def list_interview_agents_for_dashboard(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.survey_voice_agent_service import list_dashboard_agents_for_service
    from app.core.agent_services import SERVICE_INTERVIEW

    return {
        "agents": list_dashboard_agents_for_service(db, service_key=SERVICE_INTERVIEW, org_id=principal.org_id),
    }


@router.post("/interview/draft")
def ensure_interview_draft(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.interview_intake_service import ensure_interview_draft_order, intake_summary, list_intake_recipients

    order = ensure_interview_draft_order(
        db,
        org_id=principal.org_id,
        user_id=principal.user_id,
        title=str(payload.get("title") or "Interview draft"),
        role=str(payload.get("role") or ""),
        criteria=str(payload.get("criteria") or ""),
    )
    recipients = list_intake_recipients(db, order)
    return {
        "order": ServiceOrderService.order_to_dict(order),
        "recipients": recipients,
        "summary": intake_summary(recipients),
    }


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


@router.get("/{order_id}")
def get_order(order_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    recipients = ServiceOrderService.get_recipients(db, order.id)
    return ServiceOrderService.order_to_dict(order, include_recipients=True, recipients=recipients)


@router.patch("/{order_id}")
def patch_order(order_id: str, payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
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
    order = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        order = ServiceOrderService.quote_order(db, order)
        return ServiceOrderService.order_to_dict(order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


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
