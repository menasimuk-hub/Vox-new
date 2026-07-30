"""Customer dashboard API — Smart Card QR."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.plan_price import PlanPrice
from app.models.smart_card import SMART_CARD_SERVICE_CODE, SmartCardPackage, SmartCardQuestionTemplate
from app.services.org_enabled_services import is_service_enabled, org_service_maps
from app.services.org_rbac import OrgRbacService, can_view_all_campaigns
from app.services.smart_card.company_service import SmartCardCompanyService, SmartCardEntitlementService
from app.services.smart_card.representative_service import SmartCardRepError, SmartCardRepresentativeService

router = APIRouter(prefix="/smart-card", tags=["smart-card"])


def _require_smart_card_enabled(db: Session, org_id: str) -> None:
    org = db.get(Organisation, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    _allowed, _enabled, visible = org_service_maps(org, db)
    if not is_service_enabled(visible, "smart_card"):
        raise HTTPException(status_code=403, detail="Smart Card QR is not enabled for this organisation.")


def _require_manage(db: Session, principal) -> None:
    try:
        OrgRbacService.assert_can_manage_team(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.get("/entitlement")
def get_entitlement(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    mode = SmartCardEntitlementService.access_mode(db, principal.org_id)
    company = SmartCardCompanyService.get_or_create(db, principal.org_id)
    sub = SmartCardEntitlementService.active_subscription(db, principal.org_id)
    return {
        "ok": True,
        "mode": mode,
        "seat_quantity": SmartCardEntitlementService.seat_quantity(db, principal.org_id),
        "active_reps": SmartCardEntitlementService.active_rep_count(db, principal.org_id),
        "preview_tests_used": int(company.preview_tests_used or 0),
        "preview_tests_limit": 15,
        "period_end": sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
        "subscription_id": sub.id if sub else None,
    }


@router.get("/company")
def get_company(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    company = SmartCardCompanyService.get_or_create(db, principal.org_id)
    db.commit()
    return {"ok": True, "company": SmartCardCompanyService.serialize(company)}


@router.patch("/company")
def patch_company(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    _require_manage(db, principal)
    company = SmartCardCompanyService.update(db, principal.org_id, payload or {})
    db.commit()
    return {"ok": True, "company": SmartCardCompanyService.serialize(company)}


@router.get("/questions")
def list_questions(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    rows = (
        db.execute(
            select(SmartCardQuestionTemplate)
            .where(SmartCardQuestionTemplate.is_active.is_(True))
            .order_by(SmartCardQuestionTemplate.sort_order.asc())
        )
        .scalars()
        .all()
    )
    return {
        "ok": True,
        "items": [
            {
                "question_key": r.question_key,
                "label": r.label,
                "prompt": r.prompt,
                "description": r.description,
                "kind": r.kind,
                "sort_order": r.sort_order,
            }
            for r in rows
        ],
    }


@router.get("/packages")
def list_packages(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    org = db.get(Organisation, principal.org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    _allowed, _enabled, visible = org_service_maps(org, db)
    if not is_service_enabled(visible, "smart_card"):
        try:
            OrgRbacService.assert_can_access_billing(db, org_id=principal.org_id, user_id=principal.user_id)
        except PermissionError as e:
            raise HTTPException(status_code=403, detail="Smart Card QR is not enabled for this organisation.") from e

    pkgs = (
        db.execute(
            select(SmartCardPackage, Plan)
            .join(Plan, Plan.id == SmartCardPackage.plan_id)
            .where(SmartCardPackage.is_active.is_(True), Plan.is_active.is_(True))
            .order_by(SmartCardPackage.display_order.asc())
        )
        .all()
    )
    items = []
    for sc_pkg, plan in pkgs:
        prices = (
            db.execute(select(PlanPrice).where(PlanPrice.plan_id == plan.id)).scalars().all()
        )
        items.append(
            {
                "id": sc_pkg.id,
                "plan_id": plan.id,
                "code": plan.code,
                "name": plan.name,
                "description": plan.description,
                "tier": sc_pkg.tier,
                "interval": plan.interval,
                "features": plan.features_json,
                "prices": [
                    {
                        "currency": p.currency,
                        "monthly_price_minor": p.monthly_price_minor,
                        "yearly_price_minor": p.yearly_price_minor,
                    }
                    for p in prices
                ],
            }
        )
    return {"ok": True, "items": items, "service_kind": SMART_CARD_SERVICE_CODE}


@router.get("/representatives")
def list_reps(
    q: str | None = Query(None),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    _require_smart_card_enabled(db, principal.org_id)
    rows = SmartCardRepresentativeService.list_for_user(
        db, org_id=principal.org_id, user_id=principal.user_id, q=q
    )
    return {
        "ok": True,
        "items": [SmartCardRepresentativeService.serialize(db, r) for r in rows],
    }


@router.post("/representatives")
def create_rep(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    _require_manage(db, principal)
    try:
        rep = SmartCardRepresentativeService.create(
            db, org_id=principal.org_id, user_id=principal.user_id, payload=payload or {}
        )
        db.commit()
        return {"ok": True, "item": SmartCardRepresentativeService.serialize(db, rep)}
    except SmartCardRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/representatives/{rep_id}")
def get_rep(rep_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    rep = SmartCardRepresentativeService.get(db, org_id=principal.org_id, rep_id=rep_id)
    if rep is None:
        raise HTTPException(status_code=404, detail="Representative not found")
    role = OrgRbacService.role_for(db, org_id=principal.org_id, user_id=principal.user_id)
    if not can_view_all_campaigns(role) and rep.linked_user_id != principal.user_id:
        raise HTTPException(status_code=404, detail="Representative not found")
    return {"ok": True, "item": SmartCardRepresentativeService.serialize(db, rep)}


@router.patch("/representatives/{rep_id}")
def patch_rep(rep_id: str, payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    _require_smart_card_enabled(db, principal.org_id)
    _require_manage(db, principal)
    try:
        rep = SmartCardRepresentativeService.update(
            db, org_id=principal.org_id, rep_id=rep_id, payload=payload or {}
        )
        db.commit()
        return {"ok": True, "item": SmartCardRepresentativeService.serialize(db, rep)}
    except SmartCardRepError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
