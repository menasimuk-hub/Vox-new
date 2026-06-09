from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_BILLING, CAP_ORG_OPS, require_cap
from app.core.database import get_db
from app.models.platform_service import PlatformService
from app.models.service_order import ServiceOrder
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService
from app.services.zoom_service import ZoomService

router = APIRouter(prefix="/admin/platform-services", tags=["admin-platform-services"])


def _service_out(svc: PlatformService) -> dict:
    return {
        "id": svc.id,
        "code": svc.code,
        "name": svc.name,
        "description": svc.description,
        "service_kind": svc.service_kind,
        "is_active": svc.is_active,
        "sort_order": svc.sort_order,
    }


@router.get("")
def admin_list_services(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    PlatformCatalogService.ensure_defaults(db)
    services = db.execute(select(PlatformService).order_by(PlatformService.sort_order.asc())).scalars().all()
    return [_service_out(svc) for svc in services]


@router.put("/{service_id}")
def admin_update_service(service_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    svc = db.execute(select(PlatformService).where(PlatformService.id == service_id)).scalar_one_or_none()
    if svc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    if "name" in payload:
        svc.name = str(payload["name"]).strip()
    if "description" in payload:
        svc.description = str(payload.get("description") or "").strip() or None
    if "is_active" in payload:
        svc.is_active = bool(payload["is_active"])
    if "sort_order" in payload:
        svc.sort_order = int(payload["sort_order"] or 100)
    svc.updated_at = datetime.utcnow()
    db.add(svc)
    db.commit()
    db.refresh(svc)
    return _service_out(svc)


@router.post("/quote-preview")
def admin_quote_preview(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    """Estimate a campaign cost with the new per-currency pricing (plan_prices)."""
    try:
        return PlatformCatalogService.calculate_quote(
            db,
            service_code=str(payload.get("service_code") or ""),
            recipient_count=int(payload.get("recipient_count") or 0),
            options=payload.get("options") or {},
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/surveys/overview")
def admin_surveys_overview(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    return ServiceOrderService.survey_operations_overview(db)


@router.get("/surveys/wa-observability/overview")
def admin_wa_survey_observability_overview(
    order_id: str | None = None,
    org_id: str | None = None,
    survey_type_id: str | None = None,
    since_days: int = 7,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.survey_wa_observability_service import SurveyWaObservabilityService

    return SurveyWaObservabilityService.overview(
        db,
        order_id=order_id,
        org_id=org_id,
        survey_type_id=survey_type_id,
        since_days=since_days,
    )


@router.get("/surveys/wa-sessions")
def admin_wa_survey_sessions(
    order_id: str | None = None,
    org_id: str | None = None,
    survey_type_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.survey_wa_observability_service import SurveyWaObservabilityService

    return SurveyWaObservabilityService.list_sessions(
        db,
        order_id=order_id,
        org_id=org_id,
        survey_type_id=survey_type_id,
        status=status,
        limit=limit,
    )


@router.get("/surveys/wa-sessions/{session_id}")
def admin_wa_survey_session_detail(
    session_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.survey_wa_observability_service import SurveyWaObservabilityService

    detail = SurveyWaObservabilityService.get_session_detail(db, session_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return detail


@router.get("/interviews/overview")
def admin_interviews_overview(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    return ServiceOrderService.interview_operations_overview(db)


@router.get("/orders/{order_id}/audit")
def admin_order_audit(order_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    order = ServiceOrderService.get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return {"order_id": order.id, "timeline": ServiceOrderService.order_audit_timeline(order)}


@router.get("/orders/{order_id}/recipients/{recipient_id}/cv")
def admin_download_recipient_cv(
    order_id: str,
    recipient_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from fastapi.responses import FileResponse, Response

    from app.models.service_order import ServiceOrderRecipient
    from app.services.career_cv_storage_service import cv_media_type, resolve_cv_path

    order = ServiceOrderService.get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.service_code != "interview":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CV download is only for interview orders")
    recipient = db.get(ServiceOrderRecipient, recipient_id)
    if recipient is None or recipient.order_id != order.id:
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


@router.get("/orders/{order_id}/recipients/{recipient_id}/activity")
def admin_recipient_activity(
    order_id: str,
    recipient_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.models.service_order import ServiceOrderRecipient
    from app.services.interview_activity_service import InterviewActivityService

    order = ServiceOrderService.get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.service_code != "interview":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Activity timeline is only for interview orders")
    recipient = db.get(ServiceOrderRecipient, recipient_id)
    if recipient is None or recipient.order_id != order.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    return InterviewActivityService.timeline(db, order, recipient)


@router.get("/orders/{order_id}/recipients/{recipient_id}/interview-candidate-report.html")
def admin_interview_candidate_report_html(
    order_id: str,
    recipient_id: str,
    include_cv: bool = False,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.models.service_order import ServiceOrderRecipient
    from app.services.interview_candidate_report_export_service import InterviewCandidateReportExportService
    from fastapi.responses import HTMLResponse

    order = ServiceOrderService.get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    recipient = db.get(ServiceOrderRecipient, recipient_id)
    if recipient is None or recipient.order_id != order.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    html_doc = InterviewCandidateReportExportService.html(db, order, recipient, include_cv=include_cv)
    return HTMLResponse(content=html_doc)


@router.get("/orders/{order_id}/recipients/{recipient_id}/interview-candidate-report.pdf")
def admin_interview_candidate_report_pdf(
    order_id: str,
    recipient_id: str,
    include_cv: bool = False,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.models.service_order import ServiceOrderRecipient
    from app.services.interview_candidate_report_export_service import InterviewCandidateReportExportService
    from fastapi.responses import Response

    order = ServiceOrderService.get_order(db, order_id)
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


@router.post("/orders/{order_id}/send-invites")
def admin_send_interview_invites(
    order_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.interview_booking_service import InterviewBookingService

    order = ServiceOrderService.get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.service_code != "interview":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invites are only for interview orders")
    body = payload or {}
    try:
        force = bool(body.get("force_resend", True))
        return InterviewBookingService.send_invites(
            db,
            order,
            recipient_ids=body.get("recipient_ids"),
            channels=body.get("channels"),
            force_resend=force,
            force_email=bool(body.get("force_email", force)),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/orders/{order_id}/recipients/{recipient_id}")
def admin_get_recipient_detail(
    order_id: str,
    recipient_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.models.service_order import ServiceOrderRecipient
    from app.services.survey_results_service import SurveyResultsService

    order = ServiceOrderService.get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    recipient = db.get(ServiceOrderRecipient, recipient_id)
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    try:
        detail = SurveyResultsService.get_recipient_detail(db, order, recipient)
        detail["contact"] = ServiceOrderService.recipient_to_dict(recipient)
        from app.models.survey_session import SurveySession
        from app.services.survey_wa_observability_service import SurveyWaObservabilityService

        wa_session = db.execute(
            select(SurveySession).where(SurveySession.recipient_id == recipient_id).limit(1)
        ).scalar_one_or_none()
        if wa_session is not None:
            try:
                detail["wa_survey_session"] = SurveyWaObservabilityService.get_session_detail(
                    db, wa_session.id
                )
            except ValueError:
                detail["wa_survey_session"] = None
        return detail
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.patch("/orders/{order_id}/recipients/{recipient_id}")
def admin_update_recipient(
    order_id: str,
    recipient_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.models.service_order import ServiceOrderRecipient

    order = ServiceOrderService.get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    recipient = db.get(ServiceOrderRecipient, recipient_id)
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    try:
        recipient = ServiceOrderService.update_recipient(db, order, recipient, payload or {})
        return {"ok": True, "recipient": ServiceOrderService.recipient_to_dict(recipient)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/orders")
def admin_list_orders(
    payment_status: str | None = None,
    status_filter: str | None = None,
    service_code: str | None = None,
    org_id: str | None = None,
    live_only: bool = False,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    stmt = select(ServiceOrder).order_by(ServiceOrder.created_at.desc()).limit(200)
    if payment_status:
        stmt = stmt.where(ServiceOrder.payment_status == payment_status)
    if status_filter:
        stmt = stmt.where(ServiceOrder.status == status_filter)
    if service_code:
        stmt = stmt.where(ServiceOrder.service_code == service_code)
    if org_id:
        stmt = stmt.where(ServiceOrder.org_id == org_id)
    rows = list(db.execute(stmt).scalars())
    if live_only:
        rows = [r for r in rows if r.service_code == "survey" and ServiceOrderService.is_live_survey(r)]
    return [ServiceOrderService.order_to_admin_dict(db, r) for r in rows]


@router.get("/orders/{order_id}")
def admin_get_order(order_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    order = ServiceOrderService.get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    recipients = ServiceOrderService.get_recipients(db, order.id)
    return ServiceOrderService.order_to_admin_dict(db, order, include_recipients=True, recipients=recipients)


@router.post("/orders/{order_id}/dial-next")
def admin_dial_next(order_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    from app.services.survey_call_dispatch_service import SurveyCallDispatchService

    order = ServiceOrderService.get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.status != "running":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Survey must be running")
    row = SurveyCallDispatchService.dial_next_recipient(db, order)
    if row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No contact ready to dial")
    recipients = ServiceOrderService.get_recipients(db, order.id)
    return ServiceOrderService.order_to_admin_dict(db, order, include_recipients=True, recipients=recipients)


@router.post("/orders/{order_id}/recipients/{recipient_id}/call-now")
def admin_call_recipient_now(
    order_id: str,
    recipient_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.models.service_order import ServiceOrderRecipient
    from app.services.survey_call_dispatch_service import SurveyCallDispatchService

    order = ServiceOrderService.get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    recipient = db.get(ServiceOrderRecipient, recipient_id)
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    try:
        SurveyCallDispatchService.dial_recipient(
            db,
            order,
            recipient,
            retry=bool((payload or {}).get("retry")),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    db.refresh(order)
    recipients = ServiceOrderService.get_recipients(db, order.id)
    return ServiceOrderService.order_to_admin_dict(db, order, include_recipients=True, recipients=recipients)


@router.post("/orders/{order_id}/reanalyze")
def admin_reanalyze_order(order_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    from app.services.survey_analysis_service import SurveyAnalysisService

    order = ServiceOrderService.get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        result = SurveyAnalysisService.reanalyze_order(db, order=order)
        recipients = ServiceOrderService.get_recipients(db, order.id)
        payload = ServiceOrderService.order_to_admin_dict(db, order, include_recipients=True, recipients=recipients)
        payload["reanalyze"] = result
        return payload
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/orders/{order_id}/recipients/{recipient_id}/reanalyze")
def admin_reanalyze_recipient(
    order_id: str,
    recipient_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.models.service_order import ServiceOrderRecipient
    from app.services.survey_analysis_service import SurveyAnalysisService

    order = ServiceOrderService.get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    recipient = db.get(ServiceOrderRecipient, recipient_id)
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    try:
        SurveyAnalysisService.reanalyze_recipient(db, order=order, recipient=recipient)
        recipients = ServiceOrderService.get_recipients(db, order.id)
        return ServiceOrderService.order_to_admin_dict(db, order, include_recipients=True, recipients=recipients)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/orders/{order_id}/start")
def admin_start_order(order_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    order = ServiceOrderService.get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        order = ServiceOrderService.start_order(db, order)
        return ServiceOrderService.order_to_admin_dict(db, order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/orders/{order_id}/pause")
def admin_pause_order(order_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    order = ServiceOrderService.get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        order = ServiceOrderService.pause_order(db, order)
        return ServiceOrderService.order_to_admin_dict(db, order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/orders/{order_id}/resume")
def admin_resume_order(order_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    order = ServiceOrderService.get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        order = ServiceOrderService.resume_order(db, order)
        return ServiceOrderService.order_to_admin_dict(db, order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/orders/{order_id}/stop")
def admin_stop_order(order_id: str, payload: dict | None = None, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    order = ServiceOrderService.get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        order = ServiceOrderService.stop_order(db, order, reason=str((payload or {}).get("reason") or "Stopped by admin"))
        return ServiceOrderService.order_to_admin_dict(db, order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/orders/{order_id}/approve-payment")
def admin_approve_order_payment(
    order_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    order = ServiceOrderService.get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        order = ServiceOrderService.admin_approve_payment(db, order, note=str((payload or {}).get("note") or ""))
        return ServiceOrderService.order_to_admin_dict(db, order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/orders/{order_id}/reject-payment")
def admin_reject_order_payment(
    order_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    order = ServiceOrderService.get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        order = ServiceOrderService.admin_reject_payment(db, order, note=str((payload or {}).get("note") or ""))
        return ServiceOrderService.order_to_admin_dict(db, order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/integrations/zoom/test")
def admin_test_zoom(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    try:
        return ZoomService.test_connection(db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
