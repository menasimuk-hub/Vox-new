"""Apply script moderation gates on interview/survey draft saves and admin review."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder
from app.services.moderation import is_moderation_enabled, moderate_content


def loads_order_config(order: ServiceOrder | None) -> dict[str, Any]:
    if order is None:
        return {}
    try:
        cfg = json.loads(order.config_json or "{}")
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def resolve_script_text(cfg: dict[str, Any], *, fallback: dict[str, Any] | None = None) -> str:
    for source in (cfg, fallback or {}):
        for key in ("approved_script", "generated_script_draft", "script"):
            value = str(source.get(key) or "").strip()
            if value:
                return value
    return ""


def script_moderation_blocks_launch(config: dict[str, Any]) -> str | None:
    status = str(config.get("script_moderation_status") or "").strip().lower()
    if status == "pending_admin_review":
        reason = str(config.get("script_moderation_reason") or "Content review required.").strip()
        return (
            f"Script pending admin review: {reason} "
            "Edit the text and approve again, or wait for VoxBulk approval."
        )
    if status == "rejected":
        reason = str(config.get("script_moderation_reason") or "Script was rejected.").strip()
        return f"Script rejected: {reason} Please edit the text and approve again."
    return None


def apply_script_moderation_gate(
    *,
    service_code: str,
    config_patch: dict[str, Any],
    previous_cfg: dict[str, Any],
    db: Session,
) -> dict[str, Any]:
    if service_code not in {"interview", "survey"}:
        return config_patch

    patch = dict(config_patch)
    prev = dict(previous_cfg or {})
    script_text = resolve_script_text(patch, fallback=prev)
    prev_script = resolve_script_text(prev)
    script_changed = script_text.strip() != prev_script.strip()

    wants_approve = patch.get("script_approved") is True
    prev_status = str(prev.get("script_moderation_status") or "").strip().lower()

    if not wants_approve and not script_changed:
        return patch

    if not script_text.strip():
        if wants_approve:
            patch["script_approved"] = False
        return patch

    if script_changed and prev_status == "approved":
        patch["script_moderation_status"] = "not_scanned"
        patch["script_approved"] = False

    # Preserve an existing approval (including an admin override) when the
    # script text is unchanged — re-scanning here would let a later autosave
    # silently revert admin approval back to pending review.
    if not script_changed and prev_status == "approved":
        patch["script_moderation_status"] = "approved"
        patch["script_moderation_category"] = prev.get("script_moderation_category") or "safe"
        patch["script_moderation_reason"] = prev.get("script_moderation_reason") or ""
        patch["script_approved"] = True
        return patch

    if not wants_approve:
        return patch

    if not is_moderation_enabled(db):
        now = datetime.utcnow().isoformat()
        patch.update(
            {
                "script_moderation_status": "approved",
                "script_moderation_category": "safe",
                "script_moderation_reason": "",
                "script_moderation_scanned_at": now,
                "script_approved": True,
            }
        )
        return patch

    result = moderate_content(script_text, db=db)
    now = datetime.utcnow().isoformat()
    patch["script_moderation_scanned_at"] = now
    patch["script_moderation_category"] = str(result.get("category") or "offensive")
    patch["script_moderation_reason"] = str(result.get("reason") or "")

    if result.get("safe"):
        patch["script_moderation_status"] = "approved"
        patch["script_approved"] = True
    else:
        patch["script_moderation_status"] = "pending_admin_review"
        patch["script_approved"] = False
    return patch


def list_script_moderation_queue(db: Session, *, limit: int = 100) -> list[dict[str, Any]]:
    stmt = (
        select(ServiceOrder)
        .where(ServiceOrder.service_code.in_(["interview", "survey"]))
        .order_by(ServiceOrder.updated_at.desc())
        .limit(500)
    )
    rows = list(db.execute(stmt).scalars())
    out: list[dict[str, Any]] = []
    for order in rows:
        cfg = loads_order_config(order)
        if str(cfg.get("script_moderation_status") or "").strip().lower() != "pending_admin_review":
            continue
        script = resolve_script_text(cfg)
        out.append(
            {
                "order_id": order.id,
                "org_id": order.org_id,
                "service_code": order.service_code,
                "title": order.title,
                "status": order.status,
                "payment_status": order.payment_status,
                "updated_at": order.updated_at.isoformat() if order.updated_at else None,
                "script_excerpt": script[:600],
                "script_moderation_category": cfg.get("script_moderation_category"),
                "script_moderation_reason": cfg.get("script_moderation_reason"),
                "script_moderation_scanned_at": cfg.get("script_moderation_scanned_at"),
            }
        )
        if len(out) >= max(1, limit):
            break
    return out


def _save_order_config(db: Session, order: ServiceOrder, cfg: dict[str, Any]) -> ServiceOrder:
    order.config_json = json.dumps(cfg, ensure_ascii=False)
    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def admin_approve_script_moderation(
    db: Session,
    order: ServiceOrder,
    *,
    admin_user_id: str,
    note: str = "",
) -> ServiceOrder:
    cfg = loads_order_config(order)
    now = datetime.utcnow().isoformat()
    approved_text = resolve_script_text(cfg)
    cfg.update(
        {
            "script_moderation_status": "approved",
            "script_moderation_category": "safe",
            "script_moderation_reason": "",
            "script_moderation_reviewed_by": admin_user_id,
            "script_moderation_reviewed_at": now,
            "script_moderation_admin_note": str(note or "").strip(),
            "approved_script": approved_text,
            "script_approved": True,
        }
    )
    return _save_order_config(db, order, cfg)


def admin_reject_script_moderation(
    db: Session,
    order: ServiceOrder,
    *,
    admin_user_id: str,
    note: str = "",
) -> ServiceOrder:
    cfg = loads_order_config(order)
    now = datetime.utcnow().isoformat()
    reason = str(note or cfg.get("script_moderation_reason") or "Rejected by admin.").strip()
    cfg.update(
        {
            "script_moderation_status": "rejected",
            "script_moderation_reason": reason,
            "script_moderation_reviewed_by": admin_user_id,
            "script_moderation_reviewed_at": now,
            "script_moderation_admin_note": reason,
            "script_approved": False,
        }
    )
    return _save_order_config(db, order, cfg)
