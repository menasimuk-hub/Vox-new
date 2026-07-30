"""Smart Card QR change requests (rep → org admin)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.smart_card import SmartCardChangeRequest, SmartCardRepresentative
from app.services.org_rbac import OrgRbacService, can_view_all_campaigns


class SmartCardChangeRequestError(ValueError):
    pass


class SmartCardChangeRequestService:
    @staticmethod
    def list_for_user(db: Session, *, org_id: str, user_id: str) -> list[dict[str, Any]]:
        role = OrgRbacService.role_for(db, org_id=org_id, user_id=user_id)
        stmt = select(SmartCardChangeRequest).where(SmartCardChangeRequest.org_id == org_id)
        if not can_view_all_campaigns(role):
            stmt = stmt.where(SmartCardChangeRequest.requested_by_user_id == user_id)
        stmt = stmt.order_by(SmartCardChangeRequest.created_at.desc()).limit(200)
        rows = db.execute(stmt).scalars().all()
        return [SmartCardChangeRequestService._ser(r) for r in rows]

    @staticmethod
    def create(db: Session, *, org_id: str, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        message = str(payload.get("message") or "").strip()
        if not message:
            raise SmartCardChangeRequestError("message is required")
        rep_id = str(payload.get("representative_id") or "").strip() or None
        if rep_id:
            rep = db.execute(
                select(SmartCardRepresentative).where(
                    SmartCardRepresentative.id == rep_id,
                    SmartCardRepresentative.org_id == org_id,
                )
            ).scalar_one_or_none()
            if rep is None:
                raise SmartCardChangeRequestError("Representative not found")
        row = SmartCardChangeRequest(
            org_id=org_id,
            representative_id=rep_id,
            requested_by_user_id=user_id,
            target_type=str(payload.get("target_type") or "general")[:32],
            target_id=(str(payload.get("target_id") or "").strip() or None),
            message=message[:4000],
            status="pending",
        )
        db.add(row)
        db.flush()
        return SmartCardChangeRequestService._ser(row)

    @staticmethod
    def resolve(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        request_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        row = db.execute(
            select(SmartCardChangeRequest).where(
                SmartCardChangeRequest.id == request_id,
                SmartCardChangeRequest.org_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise SmartCardChangeRequestError("Request not found")
        status = str(payload.get("status") or "").strip().lower()
        if status not in {"done", "rejected", "pending"}:
            raise SmartCardChangeRequestError("status must be done, rejected, or pending")
        row.status = status
        if "admin_note" in payload:
            row.admin_note = (str(payload.get("admin_note") or "").strip() or None)
        if status in {"done", "rejected"}:
            row.resolved_by_user_id = user_id
            row.resolved_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.flush()
        return SmartCardChangeRequestService._ser(row)

    @staticmethod
    def _ser(r: SmartCardChangeRequest) -> dict[str, Any]:
        return {
            "id": r.id,
            "representative_id": r.representative_id,
            "requested_by_user_id": r.requested_by_user_id,
            "target_type": r.target_type,
            "target_id": r.target_id,
            "message": r.message,
            "status": r.status,
            "admin_note": r.admin_note,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
        }
