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


@router.get("/orders")
def admin_list_orders(
    payment_status: str | None = None,
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    stmt = select(ServiceOrder).order_by(ServiceOrder.created_at.desc()).limit(200)
    if payment_status:
        stmt = stmt.where(ServiceOrder.payment_status == payment_status)
    if status_filter:
        stmt = stmt.where(ServiceOrder.status == status_filter)
    rows = list(db.execute(stmt).scalars())
    return [ServiceOrderService.order_to_dict(r) for r in rows]


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
        return ServiceOrderService.order_to_dict(order)
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
        return ServiceOrderService.order_to_dict(order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/integrations/zoom/test")
def admin_test_zoom(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    try:
        return ZoomService.test_connection(db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
