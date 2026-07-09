from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.connection_profile import (
    CHANNEL_WHATSAPP,
    ConnectionProfile,
    ConnectionProfileOrg,
    ConnectionProfileService,
)
from app.services.connection.constants import normalize_service_code


class ConnectionProfileResolver:
    @staticmethod
    def has_profiles(db: Session, *, channel: str = CHANNEL_WHATSAPP) -> bool:
        count = db.execute(
            select(func.count())
            .select_from(ConnectionProfile)
            .where(ConnectionProfile.channel == channel)
        ).scalar_one()
        return int(count or 0) > 0

    @staticmethod
    def resolve_whatsapp(
        db: Session,
        *,
        org_id: str | None = None,
        service_code: str | None = None,
    ) -> ConnectionProfile | None:
        return ConnectionProfileResolver._resolve(
            db,
            channel=CHANNEL_WHATSAPP,
            org_id=org_id,
            service_code=service_code,
        )

    @staticmethod
    def _resolve(
        db: Session,
        *,
        channel: str,
        org_id: str | None,
        service_code: str | None,
    ) -> ConnectionProfile | None:
        if not ConnectionProfileResolver.has_profiles(db, channel=channel):
            return None

        normalized_service = normalize_service_code(service_code)
        org_key = str(org_id or "").strip() or None

        if org_key:
            assigned = ConnectionProfileResolver._query_profiles(
                db,
                channel=channel,
                org_id=org_key,
                default_only=False,
                service_code=normalized_service,
            )
            if assigned:
                return assigned[0]

        defaults = ConnectionProfileResolver._query_profiles(
            db,
            channel=channel,
            org_id=None,
            default_only=True,
            service_code=normalized_service,
        )
        return defaults[0] if defaults else None

    @staticmethod
    def resolve_whatsapp_by_business_number(
        db: Session,
        *,
        to_number: str | None,
    ) -> ConnectionProfile | None:
        """Match inbound business line (Meta whatsapp_from or Telnyx number) to a profile."""
        from app.services.messaging_log_service import normalize_e164

        raw = str(to_number or "").strip()
        if not raw:
            return None
        try:
            target = normalize_e164(raw)
        except ValueError:
            target = raw

        rows = list(
            db.execute(
                select(ConnectionProfile).where(
                    ConnectionProfile.channel == CHANNEL_WHATSAPP,
                    ConnectionProfile.is_active.is_(True),
                )
            ).scalars()
        )
        for row in rows:
            for candidate in (row.meta_whatsapp_from, row.telnyx_number):
                if not candidate:
                    continue
                try:
                    if normalize_e164(str(candidate)) == target:
                        return row
                except ValueError:
                    if str(candidate).strip() == target:
                        return row
        return None

    @staticmethod
    def _query_profiles(
        db: Session,
        *,
        channel: str,
        org_id: str | None,
        default_only: bool,
        service_code: str | None,
    ) -> list[ConnectionProfile]:
        stmt = (
            select(ConnectionProfile)
            .where(ConnectionProfile.channel == channel)
            .where(ConnectionProfile.is_active.is_(True))
        )
        if default_only:
            stmt = stmt.where(ConnectionProfile.is_default.is_(True))
        elif org_id:
            stmt = stmt.join(ConnectionProfileOrg, ConnectionProfileOrg.profile_id == ConnectionProfile.id).where(
                ConnectionProfileOrg.org_id == org_id
            )
            stmt = stmt.where(ConnectionProfile.is_default.is_(False))

        stmt = stmt.order_by(ConnectionProfile.created_at.asc())
        profiles = list(db.execute(stmt).scalars().all())
        if not profiles:
            return []

        if not service_code:
            return profiles

        enabled_ids: set[str] = set()
        rows = db.execute(
            select(ConnectionProfileService.profile_id)
            .where(ConnectionProfileService.service_code == service_code)
            .where(ConnectionProfileService.enabled.is_(True))
        ).all()
        for row in rows:
            enabled_ids.add(str(row[0]))

        return [p for p in profiles if p.id in enabled_ids]
