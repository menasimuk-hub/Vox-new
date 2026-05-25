from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_BILLING, CAP_ORG_OPS, require_cap
from app.core.database import get_db
from app.models.platform_service import PlatformService, ServicePricingRule
from app.models.service_order import ServiceOrder
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService
from app.services.zoom_service import ZoomService

router = APIRouter(prefix="/admin/platform-services", tags=["admin-platform-services"])


def _rule_out(r: ServicePricingRule) -> dict:
    return PlatformCatalogService.rule_to_dict(r, include_internal=True)


@router.get("")
def admin_list_services(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    PlatformCatalogService.ensure_defaults(db)
    services = db.execute(select(PlatformService).order_by(PlatformService.sort_order.asc())).scalars().all()
    out = []
    for svc in services:
        rules = PlatformCatalogService.list_rules_for_service(db, svc.id, active_only=False)
        out.append(
            {
                "id": svc.id,
                "code": svc.code,
                "name": svc.name,
                "description": svc.description,
                "service_kind": svc.service_kind,
                "is_active": svc.is_active,
                "sort_order": svc.sort_order,
                "pricing_rules": [_rule_out(r) for r in rules],
            }
        )
    return out


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
    rules = PlatformCatalogService.list_rules_for_service(db, svc.id, active_only=False)
    return {
        "id": svc.id,
        "code": svc.code,
        "name": svc.name,
        "description": svc.description,
        "service_kind": svc.service_kind,
        "is_active": svc.is_active,
        "sort_order": svc.sort_order,
        "pricing_rules": [_rule_out(r) for r in rules],
    }


@router.post("/{service_id}/pricing-rules")
def admin_create_pricing_rule(service_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    svc = db.execute(select(PlatformService).where(PlatformService.id == service_id)).scalar_one_or_none()
    if svc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    row = ServicePricingRule(
        service_id=svc.id,
        channel=PlatformCatalogService.normalize_survey_channel(str(payload.get("channel") or "default")),
        rule_type=str(payload.get("rule_type") or "per_person"),
        label=str(payload.get("label") or "Pricing rule"),
        base_fee_pence=int(payload.get("base_fee_pence") or 0),
        unit_price_pence=int(payload.get("unit_price_pence") or 0),
        bundle_size=int(payload["bundle_size"]) if payload.get("bundle_size") else None,
        bundle_price_pence=int(payload["bundle_price_pence"]) if payload.get("bundle_price_pence") else None,
        included_units=int(payload["included_units"]) if payload.get("included_units") else None,
        overage_unit_price_pence=int(payload["overage_unit_price_pence"]) if payload.get("overage_unit_price_pence") else None,
        is_active=bool(payload.get("is_active", True)),
        sort_order=int(payload.get("sort_order") or 100),
        notes=str(payload.get("notes") or "").strip() or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _rule_out(row)


@router.put("/pricing-rules/{rule_id}")
def admin_update_pricing_rule(rule_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    row = db.execute(select(ServicePricingRule).where(ServicePricingRule.id == rule_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pricing rule not found")
    for field in (
        "rule_type",
        "label",
        "notes",
    ):
        if field in payload:
            setattr(row, field, str(payload[field]).strip())
    if "channel" in payload:
        row.channel = PlatformCatalogService.normalize_survey_channel(str(payload["channel"]))
    for field in (
        "base_fee_pence",
        "unit_price_pence",
        "bundle_size",
        "bundle_price_pence",
        "included_units",
        "overage_unit_price_pence",
        "sort_order",
    ):
        if field in payload and payload[field] is not None:
            setattr(row, field, int(payload[field]))
    if "is_active" in payload:
        row.is_active = bool(payload["is_active"])
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _rule_out(row)


@router.post("/quote-preview")
def admin_quote_preview(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
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
    from app.services.career_cv_storage_service import resolve_cv_path

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
        return FileResponse(path, filename=filename, media_type="application/octet-stream")
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
