"""Admin UK compliance settings and audit (PECR / UK GDPR baseline)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_ORG_OPS, require_cap
from app.core.database import get_db
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.services.uk_compliance_audit_service import UkComplianceAuditService
from app.services.uk_compliance_constants import ARTICLE9_CONDITIONS, LAWFUL_BASES, MESSAGE_PURPOSES
from app.services.uk_compliance_retention_service import UkComplianceRetentionService
from app.services.uk_compliance_service import UkComplianceService, org_compliance_dict

router = APIRouter(prefix="/admin/compliance", tags=["admin-compliance"])


@router.get("/schema")
def compliance_schema(_admin=Depends(require_cap(CAP_ORG_OPS))):
    return {
        "ok": True,
        "lawful_bases": sorted(LAWFUL_BASES),
        "message_purposes": sorted(MESSAGE_PURPOSES),
        "article9_conditions": sorted(ARTICLE9_CONDITIONS),
    }


@router.get("/audit")
def list_compliance_audit(
    limit: int = 100,
    event_type: str | None = None,
    org_id: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    return {
        "ok": True,
        "events": UkComplianceAuditService.list_recent(
            db, limit=limit, event_type=event_type, org_id=org_id
        ),
    }


@router.get("/organisations/{org_id}")
def get_org_compliance(
    org_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    org = db.get(Organisation, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    return {"ok": True, "org_id": org_id, "defaults": org_compliance_dict(db, org_id)}


@router.put("/organisations/{org_id}")
def update_org_compliance(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    org = db.get(Organisation, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    row = UkComplianceService.upsert_org_defaults(db, org_id, payload or {})
    UkComplianceAuditService.record(
        db,
        event_type="consent.org_defaults_updated",
        org_id=org_id,
        detail={"fields": list((payload or {}).keys())},
    )
    return {"ok": True, "defaults": org_compliance_dict(db, org_id)}


@router.get("/orders/{order_id}/readiness")
def order_compliance_readiness(
    order_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    order = db.get(ServiceOrder, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return {"ok": True, **UkComplianceService.readiness_summary(db, order)}


@router.put("/orders/{order_id}")
def update_order_compliance(
    order_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    import json

    order = db.get(ServiceOrder, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    try:
        cfg = json.loads(order.config_json or "{}")
    except Exception:
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    compliance_payload = (payload or {}).get("compliance") if isinstance(payload, dict) else payload
    if not isinstance(compliance_payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="compliance object required")
    cfg = UkComplianceService.attach_compliance_to_order_config(cfg, compliance_payload)
    order.config_json = json.dumps(cfg, ensure_ascii=False)
    db.add(order)
    db.commit()
    db.refresh(order)
    UkComplianceAuditService.record(
        db,
        event_type="consent.order_updated",
        org_id=order.org_id,
        order_id=order.id,
        detail={"fields": list(compliance_payload.keys())},
    )
    return {"ok": True, **UkComplianceService.readiness_summary(db, order)}


@router.post("/retention/run")
def run_retention_now(
    dry_run: bool = False,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    stats = UkComplianceRetentionService.run_retention_pass(db, dry_run=dry_run)
    return {"ok": True, "stats": stats}


@router.get("/contact-time")
def get_contact_time_settings(
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.contact_time_service import full_settings_payload

    return {"ok": True, **full_settings_payload(db)}


@router.put("/contact-time/calling")
def update_contact_time_calling(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.contact_time_service import full_settings_payload, update_calling_settings

    try:
        update_calling_settings(db, payload or {})
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    UkComplianceAuditService.record(
        db,
        event_type="compliance.contact_time_calling_updated",
        detail={"fields": list((payload or {}).keys())},
    )
    return {"ok": True, **full_settings_payload(db)}


@router.put("/contact-time/whatsapp")
def update_contact_time_whatsapp(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.contact_time_service import full_settings_payload, update_wa_settings

    try:
        update_wa_settings(db, payload or {})
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    UkComplianceAuditService.record(
        db,
        event_type="compliance.contact_time_wa_updated",
        detail={"fields": list((payload or {}).keys())},
    )
    return {"ok": True, **full_settings_payload(db)}
