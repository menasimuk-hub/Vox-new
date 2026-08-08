"""Smart Card QR representatives CRUD, product assignment, invites hook."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models.smart_card import (
    SmartCardProduct,
    SmartCardRepresentative,
    SmartCardRepresentativeProduct,
)
from app.services.org_rbac import ORG_TEAM_MANAGERS, OrgRbacService, can_view_all_campaigns, effective_role
from app.services.qr_style_fields import apply_qr_style_payload, qr_style_dict
from app.services.qr_style_render import (
    normalize_corner_style,
    normalize_frame_round,
    normalize_module_style,
)
from app.services.smart_card.company_service import (
    SmartCardCompanyService,
    SmartCardEntitlementService,
    build_rep_qr_token,
)

logger = logging.getLogger(__name__)

MEMBER_EDIT_KEYS = frozenset(
    {
        "name",
        "email",
        "website",
        "mobile",
        "landline",
        "extension",
        "notes",
        "social_links",
        "extra",
        "qr_fg_color",
        "qr_bg_color",
        "qr_transparent",
        "qr_module_style",
        "qr_corner_style",
        "qr_show_arrow",
        "qr_frame_round",
        "product_ids",
    }
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
            qr_module_style=normalize_module_style(payload.get("qr_module_style")),
            qr_corner_style=normalize_corner_style(payload.get("qr_corner_style")),
            qr_show_arrow=False,
            qr_frame_round=normalize_frame_round(payload.get("qr_frame_round")),
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
        if rep.email:
            try:
                SmartCardRepresentativeService.invite_or_link_rep(
                    db, org_id=org_id, actor_user_id=user_id, rep=rep
                )
            except Exception as e:
                logger.warning("smart_card_invite_on_create_failed rep=%s err=%s", rep.id, e)
        return rep

    @staticmethod
    def invite_or_link_rep(
        db: Session,
        *,
        org_id: str,
        actor_user_id: str,
        rep: SmartCardRepresentative,
        force_resend: bool = False,
    ) -> dict[str, Any]:
        """Skip admin/owner emails; link existing members; else send member invite."""
        email = (rep.email or "").strip().lower()
        if not email or "@" not in email:
            return {"action": "skipped", "reason": "no_email"}

        from app.models.membership import OrganisationMembership
        from app.models.organisation import Organisation
        from app.models.user import User
        from app.services.org_team_service import OrgTeamService
        from app.services.smart_card.email_service import SmartCardEmailService

        actor = db.get(User, actor_user_id)
        org = db.get(Organisation, org_id)
        org_name = (org.name if org else "your organisation") or "your organisation"

        existing_user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing_user is not None:
            mem = db.execute(
                select(OrganisationMembership).where(
                    OrganisationMembership.org_id == org_id,
                    OrganisationMembership.user_id == existing_user.id,
                )
            ).scalar_one_or_none()
            if mem is not None:
                role = effective_role(mem.role)
                is_admin = role in ORG_TEAM_MANAGERS or str(existing_user.id) == str(actor_user_id)
                # Always link when already in org; never send invite to owner/manager/admin.
                if not rep.linked_user_id:
                    rep.linked_user_id = existing_user.id
                    db.add(rep)
                    db.flush()
                if is_admin:
                    return {"action": "linked_admin", "linked_user_id": existing_user.id}
                return {"action": "linked_member", "linked_user_id": existing_user.id}

        if rep.linked_user_id and not force_resend:
            return {"action": "already_linked", "linked_user_id": rep.linked_user_id}

        if actor is None:
            logger.warning("smart_card_invite_skipped rep=%s reason=no_actor", rep.id)
            return {"action": "skipped", "reason": "no_actor"}

        try:
            invite = OrgTeamService.create_invite(
                db,
                org_id=org_id,
                email=email,
                role="member",
                invited_by=actor,
                send_email=False,
            )
            rep.invite_id = invite.get("invite_id")
            db.add(rep)
            db.flush()
            sent = SmartCardEmailService.send_rep_member_invite(
                db,
                to_email=email,
                rep_name=rep.name or "there",
                org_name=org_name,
                signup_url=str(invite.get("signup_url") or ""),
            )
            return {
                "action": "invited",
                "invite_id": invite.get("invite_id"),
                "email_sent": bool(sent),
                "signup_url": invite.get("signup_url"),
            }
        except ValueError as e:
            msg = str(e)
            logger.warning("smart_card_invite_failed rep=%s err=%s", rep.id, msg)
            if "already belongs" in msg.lower():
                u = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
                if u is not None:
                    rep.linked_user_id = u.id
                    db.add(rep)
                    db.flush()
                    return {"action": "linked_member", "linked_user_id": u.id}
            raise SmartCardRepError(msg) from e
        except Exception as e:
            logger.exception("smart_card_invite_unexpected rep=%s", rep.id)
            raise SmartCardRepError(f"Could not send invite: {e}") from e

    @staticmethod
    def member_safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in (payload or {}).items() if k in MEMBER_EDIT_KEYS}

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
        apply_qr_style_payload(rep, payload, allow_transparent=False)
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
            **qr_style_dict(rep, include_transparent=True),
            "photo_storage_path": rep.photo_storage_path,
            "photo_url": (
                f"/smart-card/representatives/{rep.id}/photo?v={int(rep.updated_at.timestamp()) if rep.updated_at else 0}"
                if rep.photo_storage_path
                else None
            ),
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
