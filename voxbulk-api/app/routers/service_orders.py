from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService
from app.services.gocardless_service import BillingService, GoCardlessConfigError, GoCardlessProviderError

router = APIRouter(prefix="/service-orders", tags=["service-orders"])


@router.get("/catalog")
def list_catalog(db: Session = Depends(get_db), _principal=Depends(get_current_principal)):
    services = PlatformCatalogService.list_services(db)
    out = []
    for svc in services:
        rules = PlatformCatalogService.list_rules_for_service(db, svc.id)
        out.append(
            {
                "id": svc.id,
                "code": svc.code,
                "name": svc.name,
                "description": svc.description,
                "service_kind": svc.service_kind,
                "pricing_rules": [
                    {
                        "id": r.id,
                        "channel": r.channel,
                        "rule_type": r.rule_type,
                        "label": r.label,
                        "base_fee_pence": r.base_fee_pence,
                        "unit_price_pence": r.unit_price_pence,
                        "bundle_size": r.bundle_size,
                        "bundle_price_pence": r.bundle_price_pence,
                    }
                    for r in rules
                ],
            }
        )
    return out


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
