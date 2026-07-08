"""Profile-scoped WhatsApp template push: ledger per connection profile, main row = primary only."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.connection_profile import CHANNEL_WHATSAPP, PROVIDER_TELNYX, ConnectionProfile
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.models.wa_template_profile_status import WaTemplateProfileStatus
from app.services.connection.constants import normalize_service_code
from app.services.connection.resolver import ConnectionProfileResolver
from app.services.telnyx_whatsapp_template_sync_service import (
    _LOCAL_ID_PREFIX,
    send_template_id_for_row,
)

logger = logging.getLogger(__name__)


@dataclass
class RowFieldsSnapshot:
    telnyx_record_id: str | None
    template_id: str | None
    status: str | None
    waba_id: str | None
    rejection_reason: str | None
    category: str | None
    last_push_error: str | None
    local_sync_status: str | None


@dataclass
class ProfilePushContext:
    connection_profile_id: str | None
    service_code: str
    is_primary: bool
    snapshot: RowFieldsSnapshot | None = None


class WaTemplateProfilePushService:
    @staticmethod
    def resolve_primary_connection_profile_id(
        db: Session,
        *,
        service_code: str = "survey",
    ) -> str | None:
        profile = ConnectionProfileResolver.resolve_whatsapp(
            db,
            org_id=None,
            service_code=service_code,
        )
        return str(profile.id).strip() if profile is not None else None

    @staticmethod
    def resolve_backup_connection_profile_id(
        db: Session,
        *,
        service_code: str = "survey",
    ) -> str | None:
        code = normalize_service_code(service_code) or "survey"
        primary_id = WaTemplateProfilePushService.resolve_primary_connection_profile_id(db, service_code=code)
        rows = list(
            db.execute(
                select(ConnectionProfile)
                .where(
                    ConnectionProfile.channel == CHANNEL_WHATSAPP,
                    ConnectionProfile.is_active.is_(True),
                    ConnectionProfile.provider == PROVIDER_TELNYX,
                )
                .order_by(ConnectionProfile.is_default.asc(), ConnectionProfile.name.asc())
            ).scalars()
        )
        from app.models.connection_profile import ConnectionProfileService

        for row in rows:
            if primary_id and str(row.id) == str(primary_id):
                continue
            svc = db.execute(
                select(ConnectionProfileService).where(
                    ConnectionProfileService.profile_id == row.id,
                    ConnectionProfileService.service_code == code,
                )
            ).scalar_one_or_none()
            if svc is not None and not bool(svc.enabled):
                continue
            return str(row.id)
        return None

    @staticmethod
    def resolve_active_whatsapp_profile_id(
        db: Session,
        *,
        org_id: str | None,
        service_code: str = "survey",
    ) -> str | None:
        profile = ConnectionProfileResolver.resolve_whatsapp(
            db,
            org_id=org_id,
            service_code=service_code,
        )
        return str(profile.id).strip() if profile is not None else None

    @staticmethod
    def is_primary_profile(
        db: Session,
        connection_profile_id: str | None,
        *,
        service_code: str = "survey",
    ) -> bool:
        pid = str(connection_profile_id or "").strip()
        if not pid:
            return True
        primary_id = WaTemplateProfilePushService.resolve_primary_connection_profile_id(
            db, service_code=service_code
        )
        return bool(primary_id and str(primary_id) == pid)

    @staticmethod
    def get_ledger_entry(
        db: Session,
        template_id: int,
        connection_profile_id: str | None,
    ) -> WaTemplateProfileStatus | None:
        pid = str(connection_profile_id or "").strip()
        if not pid:
            return None
        return db.execute(
            select(WaTemplateProfileStatus).where(
                WaTemplateProfileStatus.template_id == int(template_id),
                WaTemplateProfileStatus.profile_key == pid,
            )
        ).scalar_one_or_none()

    @staticmethod
    def resolve_profile_remote_context(
        db: Session,
        template_id: int,
        connection_profile_id: str | None,
        *,
        service_code: str = "survey",
    ) -> dict[str, Any]:
        entry = WaTemplateProfilePushService.get_ledger_entry(db, template_id, connection_profile_id)
        is_primary = WaTemplateProfilePushService.is_primary_profile(
            db, connection_profile_id, service_code=service_code
        )
        remote_record_id = str(entry.remote_record_id or "").strip() if entry else ""
        has_remote = bool(remote_record_id) and not remote_record_id.startswith(_LOCAL_ID_PREFIX)
        return {
            "connection_profile_id": connection_profile_id,
            "is_primary": is_primary,
            "ledger_entry": entry,
            "remote_record_id": remote_record_id or None,
            "remote_template_id": str(entry.remote_template_id or "").strip() or None if entry else None,
            "status": str(entry.status or "").strip().upper() or None if entry else None,
            "has_remote": has_remote,
        }

    @staticmethod
    def _snapshot_row(row: TelnyxWhatsappTemplate) -> RowFieldsSnapshot:
        return RowFieldsSnapshot(
            telnyx_record_id=str(row.telnyx_record_id or "").strip() or None,
            template_id=str(row.template_id or "").strip() or None,
            status=str(row.status or "").strip() or None,
            waba_id=str(row.waba_id or "").strip() or None,
            rejection_reason=str(row.rejection_reason or "").strip() or None,
            category=str(row.category or "").strip() or None,
            last_push_error=str(row.last_push_error or "").strip() or None,
            local_sync_status=str(row.local_sync_status or "").strip() or None,
        )

    @staticmethod
    def _restore_row(db: Session, row: TelnyxWhatsappTemplate, snap: RowFieldsSnapshot) -> None:
        row.telnyx_record_id = snap.telnyx_record_id
        row.template_id = snap.template_id
        row.status = snap.status
        row.waba_id = snap.waba_id
        row.rejection_reason = snap.rejection_reason
        row.category = snap.category
        row.last_push_error = snap.last_push_error
        row.local_sync_status = snap.local_sync_status
        db.add(row)

    @staticmethod
    def _ledger_has_remote(entry: WaTemplateProfileStatus | None) -> bool:
        if entry is None:
            return False
        rid = str(entry.remote_record_id or "").strip()
        return bool(rid) and not rid.startswith(_LOCAL_ID_PREFIX)

    @staticmethod
    def begin_push(
        db: Session,
        row: TelnyxWhatsappTemplate,
        *,
        connection_profile_id: str | None,
        service_code: str | None = "survey",
    ) -> ProfilePushContext:
        code = normalize_service_code(service_code) or "survey"
        pid = str(connection_profile_id or "").strip() or None
        is_primary = WaTemplateProfilePushService.is_primary_profile(db, pid, service_code=code)
        snap = WaTemplateProfilePushService._snapshot_row(row)
        if not pid:
            return ProfilePushContext(connection_profile_id=None, service_code=code, is_primary=True, snapshot=snap)

        entry = WaTemplateProfilePushService.get_ledger_entry(db, int(row.id), pid)
        if WaTemplateProfilePushService._ledger_has_remote(entry):
            row.telnyx_record_id = entry.remote_record_id
            row.template_id = entry.remote_template_id or entry.remote_record_id
            if entry.status:
                row.status = entry.status
            if entry.waba_id:
                row.waba_id = entry.waba_id
            if entry.category:
                row.category = entry.category
        elif not is_primary:
            local_id = f"{_LOCAL_ID_PREFIX}{uuid.uuid4()}"
            row.telnyx_record_id = local_id
            row.template_id = local_id
            if str(row.status or "").upper() in {"APPROVED", "PENDING", "REJECTED"}:
                row.status = "LOCAL_DRAFT"
        db.add(row)
        db.flush()
        return ProfilePushContext(
            connection_profile_id=pid,
            service_code=code,
            is_primary=is_primary,
            snapshot=snap,
        )

    @staticmethod
    def abort_push(db: Session, row: TelnyxWhatsappTemplate, ctx: ProfilePushContext) -> None:
        if ctx.is_primary or not ctx.snapshot:
            return
        WaTemplateProfilePushService._restore_row(db, row, ctx.snapshot)
        db.add(row)
        try:
            db.flush()
        except Exception:  # noqa: BLE001
            logger.exception("wa_profile_push_abort_restore_failed template_id=%s", row.id)

    @staticmethod
    def finalize_push(
        db: Session,
        row: TelnyxWhatsappTemplate,
        ctx: ProfilePushContext,
        *,
        mark_pushed: bool = True,
    ) -> None:
        from app.services.wa_template_profile_status_service import WaTemplateProfileStatusService

        pid = ctx.connection_profile_id
        if not pid:
            WaTemplateProfilePushService.record_ledger_from_row(
                db, row, connection_profile_id=None, mark_pushed=mark_pushed
            )
            return

        if ctx.is_primary:
            WaTemplateProfilePushService.record_ledger_from_row(
                db, row, connection_profile_id=pid, mark_pushed=mark_pushed
            )
            return

        push_snap = WaTemplateProfilePushService._snapshot_row(row)
        if ctx.snapshot:
            WaTemplateProfilePushService._restore_row(db, row, ctx.snapshot)
            db.add(row)
            db.flush()
        row.telnyx_record_id = push_snap.telnyx_record_id
        row.template_id = push_snap.template_id
        row.status = push_snap.status
        row.waba_id = push_snap.waba_id
        row.rejection_reason = push_snap.rejection_reason
        row.category = push_snap.category
        WaTemplateProfileStatusService.record_from_row(
            db, row, connection_profile_id=pid, mark_pushed=mark_pushed, commit=False
        )
        if ctx.snapshot:
            WaTemplateProfilePushService._restore_row(db, row, ctx.snapshot)
            db.add(row)

    @staticmethod
    def record_ledger_from_row(
        db: Session,
        row: TelnyxWhatsappTemplate,
        *,
        connection_profile_id: str | None,
        mark_pushed: bool = False,
    ) -> None:
        from app.services.wa_template_profile_status_service import WaTemplateProfileStatusService

        WaTemplateProfileStatusService.record_from_row(
            db,
            row,
            connection_profile_id=connection_profile_id,
            mark_pushed=mark_pushed,
            commit=False,
        )

    @staticmethod
    def send_template_id_for_active_profile(
        db: Session,
        row: TelnyxWhatsappTemplate,
        *,
        org_id: str | None,
        service_code: str = "survey",
    ) -> str:
        profile_id = WaTemplateProfilePushService.resolve_active_whatsapp_profile_id(
            db, org_id=org_id, service_code=service_code
        )
        if not profile_id:
            return send_template_id_for_row(row)
        entry = WaTemplateProfilePushService.get_ledger_entry(db, int(row.id), profile_id)
        if WaTemplateProfilePushService._ledger_has_remote(entry):
            return str(entry.remote_record_id).strip()
        if WaTemplateProfilePushService.is_primary_profile(db, profile_id, service_code=service_code):
            return send_template_id_for_row(row)
        remote_template_id = str(entry.remote_template_id or "").strip() if entry else ""
        return remote_template_id or send_template_id_for_row(row)
