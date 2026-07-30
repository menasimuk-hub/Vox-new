"""Smart Card QR representatives CRUD, product assignment, invites hook."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.smart_card import (
    SmartCardProduct,
    SmartCardRepresentative,
    SmartCardRepresentativeProduct,
)
from app.services.org_rbac import OrgRbacService, can_view_all_campaigns
from app.services.smart_card.company_service import (
    SmartCardCompanyService,
    SmartCardEntitlementService,
    build_rep_qr_token,
)


class SmartCardRepError(ValueError):
    pass


class SmartCardRepresentativeService:
    @staticmethod
    def list_for_user(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        q: str | None = None,
    ) -> list[SmartCardRepresentative]:
        role = OrgRbacService.role_for(db, org_id=org_id, user_id=user_id)
        stmt = select(SmartCardRepresentative).where(SmartCardRepresentative.org_id == org_id)
        if not can_view_all_campaigns(role):
            stmt = stmt.where(SmartCardRepresentative.linked_user_id == user_id)
        if q and str(q).strip():
            like = f"%{str(q).strip()}%"
            stmt = stmt.where(
                or_(
                    SmartCardRepresentative.name.ilike(like),
                    SmartCardRepresentative.email.ilike(like),
                    SmartCardRepresentative.mobile.ilike(like),
                )
            )
        stmt = stmt.order_by(SmartCardRepresentative.name.asc())
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def get(db: Session, *, org_id: str, rep_id: str) -> SmartCardRepresentative | None:
        return db.execute(
            select(SmartCardRepresentative).where(
                SmartCardRepresentative.id == rep_id,
                SmartCardRepresentative.org_id == org_id,
            )
        ).scalar_one_or_none()

    @staticmethod
    def create(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        payload: dict[str, Any],
    ) -> SmartCardRepresentative:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise SmartCardRepError("name is required")
        seats = SmartCardEntitlementService.seat_quantity(db, org_id)
        active = SmartCardEntitlementService.active_rep_count(db, org_id)
        # Allow creating reps in preview without seats, but cap active to seats when live.
        if seats > 0 and active >= seats:
            raise SmartCardRepError(
                f"Seat limit reached ({seats}). Buy more seats or archive a representative."
            )
        company = SmartCardCompanyService.get_or_create(db, org_id)
        token = build_rep_qr_token(company_slug=company.name or org_id[:8], rep_name=name)
        while (
            db.execute(
                select(SmartCardRepresentative).where(SmartCardRepresentative.qr_token == token)
            ).scalar_one_or_none()
            is not None
        ):
            token = build_rep_qr_token(company_slug=company.name or org_id[:8], rep_name=name)

        social = payload.get("social_links")
        extra = payload.get("extra")
        rep = SmartCardRepresentative(
            org_id=org_id,
            name=name,
            email=(str(payload.get("email") or "").strip().lower() or None),
            website=(str(payload.get("website") or "").strip() or None),
            social_links_json=json.dumps(social) if social is not None else None,
            mobile=(str(payload.get("mobile") or "").strip() or None),
            landline=(str(payload.get("landline") or "").strip() or None),
            extension=(str(payload.get("extension") or "").strip() or None),
            notes=(str(payload.get("notes") or "").strip() or None),
            extra_json=json.dumps(extra) if extra is not None else None,
            qr_token=token,
            qr_fg_color=str(payload.get("qr_fg_color") or "000000").replace("#", "")[:6],
            qr_bg_color=str(payload.get("qr_bg_color") or "ffffff").replace("#", "")[:6],
            qr_transparent=bool(payload.get("qr_transparent")),
            status="active",
            created_by_user_id=user_id,
        )
        db.add(rep)
        db.flush()
        product_ids = payload.get("product_ids")
        if isinstance(product_ids, list):
            SmartCardRepresentativeService.set_products(
                db, org_id=org_id, representative_id=rep.id, product_ids=[str(x) for x in product_ids]
            )
        return rep

    @staticmethod
    def update(
        db: Session,
        *,
        org_id: str,
        rep_id: str,
        payload: dict[str, Any],
    ) -> SmartCardRepresentative:
        rep = SmartCardRepresentativeService.get(db, org_id=org_id, rep_id=rep_id)
        if rep is None:
            raise SmartCardRepError("Representative not found")
        for key in ("name", "email", "website", "mobile", "landline", "extension", "notes"):
            if key in payload:
                val = payload[key]
                if key == "email" and val:
                    val = str(val).strip().lower()
                elif val is not None:
                    val = str(val).strip()
                setattr(rep, key, val or None)
        if "name" in payload and not (rep.name or "").strip():
            raise SmartCardRepError("name is required")
        if "social_links" in payload:
            rep.social_links_json = json.dumps(payload.get("social_links") or {})
        if "extra" in payload:
            rep.extra_json = json.dumps(payload.get("extra") or {})
        if "qr_fg_color" in payload:
            rep.qr_fg_color = str(payload.get("qr_fg_color") or "000000").replace("#", "")[:6]
        if "qr_bg_color" in payload:
            rep.qr_bg_color = str(payload.get("qr_bg_color") or "ffffff").replace("#", "")[:6]
        if "qr_transparent" in payload:
            rep.qr_transparent = bool(payload.get("qr_transparent"))
        if "status" in payload:
            status = str(payload.get("status") or "").strip().lower()
            if status in {"active", "archived"}:
                if status == "active" and rep.status != "active":
                    seats = SmartCardEntitlementService.seat_quantity(db, org_id)
                    active = SmartCardEntitlementService.active_rep_count(db, org_id)
                    if seats > 0 and active >= seats:
                        raise SmartCardRepError("Seat limit reached — cannot restore representative")
                rep.status = status
        if "product_ids" in payload and isinstance(payload.get("product_ids"), list):
            SmartCardRepresentativeService.set_products(
                db,
                org_id=org_id,
                representative_id=rep.id,
                product_ids=[str(x) for x in payload["product_ids"]],
            )
        rep.updated_at = datetime.utcnow()
        db.add(rep)
        db.flush()
        return rep

    @staticmethod
    def set_products(
        db: Session,
        *,
        org_id: str,
        representative_id: str,
        product_ids: list[str],
    ) -> None:
        db.execute(
            delete(SmartCardRepresentativeProduct).where(
                SmartCardRepresentativeProduct.representative_id == representative_id,
                SmartCardRepresentativeProduct.org_id == org_id,
            )
        )
        seen: set[str] = set()
        for pid in product_ids:
            pid = str(pid or "").strip()
            if not pid or pid in seen:
                continue
            seen.add(pid)
            prod = db.execute(
                select(SmartCardProduct).where(
                    SmartCardProduct.id == pid,
                    SmartCardProduct.org_id == org_id,
                )
            ).scalar_one_or_none()
            if prod is None:
                continue
            db.add(
                SmartCardRepresentativeProduct(
                    org_id=org_id,
                    representative_id=representative_id,
                    product_id=pid,
                )
            )
        db.flush()

    @staticmethod
    def product_ids(db: Session, *, representative_id: str) -> list[str]:
        rows = db.execute(
            select(SmartCardRepresentativeProduct.product_id).where(
                SmartCardRepresentativeProduct.representative_id == representative_id
            )
        ).scalars().all()
        return [str(x) for x in rows]

    @staticmethod
    def serialize(db: Session, rep: SmartCardRepresentative) -> dict[str, Any]:
        social = None
        if rep.social_links_json:
            try:
                social = json.loads(rep.social_links_json)
            except Exception:
                social = None
        extra = None
        if rep.extra_json:
            try:
                extra = json.loads(rep.extra_json)
            except Exception:
                extra = None
        web_url = SmartCardCompanyService.public_web_url(rep.qr_token)
        return {
            "id": rep.id,
            "org_id": rep.org_id,
            "name": rep.name,
            "email": rep.email,
            "website": rep.website,
            "social_links": social,
            "mobile": rep.mobile,
            "landline": rep.landline,
            "extension": rep.extension,
            "notes": rep.notes,
            "extra": extra,
            "qr_token": rep.qr_token,
            "qr_fg_color": rep.qr_fg_color,
            "qr_bg_color": rep.qr_bg_color,
            "qr_transparent": bool(rep.qr_transparent),
            "qr_image_url": SmartCardCompanyService.qr_image_url(rep),
            "web_url": web_url,
            "status": rep.status,
            "scan_count": int(rep.scan_count or 0),
            "linked_user_id": rep.linked_user_id,
            "invite_id": rep.invite_id,
            "product_ids": SmartCardRepresentativeService.product_ids(db, representative_id=rep.id),
            "created_at": rep.created_at.isoformat() if rep.created_at else None,
            "updated_at": rep.updated_at.isoformat() if rep.updated_at else None,
        }
