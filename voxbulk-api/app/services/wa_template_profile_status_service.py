"""Populate and read the per-connection-profile WhatsApp template status registry.

This is an additive ledger: after the existing sync logic writes approval
status/remote IDs onto the single ``telnyx_whatsapp_templates`` row for the
profile that was just synced, we snapshot those values into
``wa_template_profile_status`` keyed by that profile. Reusing the row's
freshly-written values means we inherit all existing status logic instead of
re-deriving it here.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.connection_profile import ConnectionProfile
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.models.wa_template_profile_status import (
    PLATFORM_PROFILE_KEY,
    WaTemplateProfileStatus,
)

logger = logging.getLogger(__name__)


class WaTemplateProfileStatusService:
    @staticmethod
    def _resolve_identity(
        db: Session, connection_profile_id: str | None
    ) -> tuple[str, str | None, str | None, str | None]:
        """Return (profile_key, connection_profile_id, provider, label)."""
        pid = str(connection_profile_id or "").strip() or None
        if pid:
            profile = db.get(ConnectionProfile, pid)
            if profile is not None:
                label = str(profile.label or profile.name or "").strip() or None
                return pid, pid, (profile.provider or None), label
            # Unknown id — still key by it so history is not lost.
            return pid, pid, None, None
        return PLATFORM_PROFILE_KEY, None, None, "Platform default"

    @staticmethod
    def record_from_row(
        db: Session,
        row: TelnyxWhatsappTemplate,
        *,
        connection_profile_id: str | None,
        mark_pushed: bool = False,
        commit: bool = False,
    ) -> WaTemplateProfileStatus | None:
        """Upsert one registry row from the template's current (freshly synced) values."""
        if row is None or row.id is None:
            return None
        profile_key, resolved_id, provider, label = WaTemplateProfileStatusService._resolve_identity(
            db, connection_profile_id
        )
        now = datetime.utcnow()
        entry = db.execute(
            select(WaTemplateProfileStatus).where(
                WaTemplateProfileStatus.template_id == int(row.id),
                WaTemplateProfileStatus.profile_key == profile_key,
            )
        ).scalar_one_or_none()
        if entry is None:
            entry = WaTemplateProfileStatus(
                template_id=int(row.id),
                profile_key=profile_key,
            )
            db.add(entry)

        entry.connection_profile_id = resolved_id
        if provider:
            entry.provider = provider
        if label:
            entry.profile_label = label
        entry.status = str(row.status or "UNKNOWN").strip().upper() or "UNKNOWN"
        entry.rejection_reason = str(row.rejection_reason or "").strip() or None
        entry.remote_record_id = str(row.telnyx_record_id or "").strip() or None
        entry.remote_template_id = str(row.template_id or "").strip() or None
        entry.waba_id = str(row.waba_id or "").strip() or None
        entry.category = str(row.category or "").strip() or None
        entry.last_synced_at = now
        entry.updated_at = now
        if mark_pushed:
            entry.last_pushed_at = row.last_pushed_at or now
            entry.last_push_error = str(row.last_push_error or "").strip() or None

        if commit:
            try:
                db.commit()
            except Exception:  # noqa: BLE001 — never let the ledger break a sync
                logger.exception("wa_template_profile_status_commit_failed template_id=%s", row.id)
                db.rollback()
        return entry

    @staticmethod
    def record_many(
        db: Session,
        rows: list[TelnyxWhatsappTemplate],
        *,
        connection_profile_id: str | None,
        mark_pushed: bool = False,
        commit: bool = True,
    ) -> int:
        count = 0
        for row in rows:
            try:
                if WaTemplateProfileStatusService.record_from_row(
                    db, row, connection_profile_id=connection_profile_id, mark_pushed=mark_pushed
                ):
                    count += 1
            except Exception:  # noqa: BLE001 — ledger is best-effort
                logger.exception("wa_template_profile_status_record_failed template_id=%s", getattr(row, "id", None))
        if commit and count:
            try:
                db.commit()
            except Exception:  # noqa: BLE001
                logger.exception("wa_template_profile_status_bulk_commit_failed")
                db.rollback()
        return count

    @staticmethod
    def _entry_to_dict(entry: WaTemplateProfileStatus) -> dict[str, Any]:
        return {
            "profile_key": entry.profile_key,
            "connection_profile_id": entry.connection_profile_id,
            "provider": entry.provider,
            "profile_label": entry.profile_label,
            "status": entry.status,
            "rejection_reason": entry.rejection_reason,
            "remote_template_id": entry.remote_template_id,
            "waba_id": entry.waba_id,
            "category": entry.category,
            "last_synced_at": entry.last_synced_at.isoformat() if entry.last_synced_at else None,
            "last_pushed_at": entry.last_pushed_at.isoformat() if entry.last_pushed_at else None,
            "last_push_error": entry.last_push_error,
        }

    @staticmethod
    def map_for_template_ids(
        db: Session, template_ids: list[int]
    ) -> dict[int, list[dict[str, Any]]]:
        """Bulk-load per-profile statuses for a set of template ids."""
        ids = [int(t) for t in template_ids if t is not None]
        if not ids:
            return {}
        rows = list(
            db.execute(
                select(WaTemplateProfileStatus)
                .where(WaTemplateProfileStatus.template_id.in_(ids))
                .order_by(
                    WaTemplateProfileStatus.template_id.asc(),
                    WaTemplateProfileStatus.profile_label.asc(),
                )
            ).scalars()
        )
        out: dict[int, list[dict[str, Any]]] = {}
        for entry in rows:
            out.setdefault(int(entry.template_id), []).append(
                WaTemplateProfileStatusService._entry_to_dict(entry)
            )
        return out

    @staticmethod
    def attach_to_dicts(db: Session, dicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Attach a ``profile_statuses`` list onto each serialized template dict (keyed by ``id``)."""
        if not dicts:
            return dicts
        ids = [int(d["id"]) for d in dicts if isinstance(d, dict) and str(d.get("id") or "").isdigit()]
        status_map = WaTemplateProfileStatusService.map_for_template_ids(db, ids)
        for d in dicts:
            if not isinstance(d, dict):
                continue
            tid = d.get("id")
            key = int(tid) if str(tid or "").isdigit() else None
            d["profile_statuses"] = status_map.get(key, []) if key is not None else []
        return dicts
