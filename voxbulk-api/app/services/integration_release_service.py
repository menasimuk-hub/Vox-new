"""Integration Testing/Live release + Admin Test group (login emails)."""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integration_tester import IntegrationTester
from app.models.partner import PartnerProvider
from app.models.provider_config import ProviderConfig

RELEASE_TESTING = "testing"
RELEASE_LIVE = "live"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Catalogue keys that may appear on FAQ.linked_provider / admin release toggles.
ORG_INTEGRATION_KEYS = frozenset(
    {
        "calendly",
        "cal_com",
        "google_calendar",
        "microsoft_calendar",
        "hubspot_meetings",
        "zoho_bookings",
        "hubspot",
        "pipedrive",
        "zoho_crm",
        "zoho_recruit",
        "breezy_hr",
    }
)

# Map catalogue tile key → provider_configs.provider when different.
ADMIN_PROVIDER_FOR_KEY = {
    "hubspot_meetings": "hubspot",
}


def normalize_email(email: str | None) -> str:
    return str(email or "").strip().lower()


def normalize_release_mode(value: str | None, *, default: str = RELEASE_TESTING) -> str:
    v = str(value or "").strip().lower()
    if v in {RELEASE_TESTING, RELEASE_LIVE}:
        return v
    return default


def release_mode_to_visible(mode: str) -> bool:
    return normalize_release_mode(mode) == RELEASE_LIVE


def visible_to_release_mode(visible: bool | None) -> str:
    return RELEASE_LIVE if bool(visible) else RELEASE_TESTING


class IntegrationReleaseService:
    @staticmethod
    def is_tester(db: Session, email: str | None) -> bool:
        norm = normalize_email(email)
        if not norm:
            return False
        row = db.execute(select(IntegrationTester.id).where(IntegrationTester.email == norm).limit(1)).scalar_one_or_none()
        return row is not None

    @staticmethod
    def list_testers(db: Session) -> list[IntegrationTester]:
        return list(
            db.execute(select(IntegrationTester).order_by(IntegrationTester.created_at.desc())).scalars().all()
        )

    @staticmethod
    def add_tester(db: Session, *, email: str, created_by_admin_user_id: str | None = None) -> IntegrationTester:
        norm = normalize_email(email)
        if not norm or not _EMAIL_RE.match(norm):
            raise ValueError("Enter a valid email address")
        existing = db.execute(select(IntegrationTester).where(IntegrationTester.email == norm)).scalar_one_or_none()
        if existing is not None:
            return existing
        row = IntegrationTester(
            email=norm,
            created_at=datetime.utcnow(),
            created_by_admin_user_id=created_by_admin_user_id,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def remove_tester(db: Session, *, tester_id: int) -> bool:
        row = db.get(IntegrationTester, tester_id)
        if row is None:
            return False
        db.delete(row)
        db.commit()
        return True

    @staticmethod
    def tester_to_dict(row: IntegrationTester) -> dict:
        return {
            "id": row.id,
            "email": row.email,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "created_by_admin_user_id": row.created_by_admin_user_id,
        }

    @staticmethod
    def _admin_provider_key(provider_key: str) -> str:
        key = str(provider_key or "").strip().lower()
        return ADMIN_PROVIDER_FOR_KEY.get(key, key)

    @staticmethod
    def get_release_mode(db: Session, provider_key: str) -> str:
        """Return testing|live for a catalogue / FAQ linked provider key."""
        key = str(provider_key or "").strip().lower()
        if not key:
            return RELEASE_LIVE
        if key == "zoho_recruit":
            partner = db.execute(select(PartnerProvider).where(PartnerProvider.key == "zoho")).scalar_one_or_none()
            if partner is None:
                return RELEASE_TESTING
            return normalize_release_mode(getattr(partner, "release_mode", None), default=RELEASE_TESTING)
        if key == "breezy_hr":
            partner = db.execute(select(PartnerProvider).where(PartnerProvider.key == "breezy")).scalar_one_or_none()
            if partner is None:
                return RELEASE_TESTING
            return normalize_release_mode(getattr(partner, "release_mode", None), default=RELEASE_TESTING)
        admin_key = IntegrationReleaseService._admin_provider_key(key)
        row = db.execute(
            select(ProviderConfig).where(
                ProviderConfig.scope == "platform",
                ProviderConfig.org_id.is_(None),
                ProviderConfig.provider == admin_key,
            )
        ).scalar_one_or_none()
        if row is None:
            return RELEASE_TESTING
        mode = normalize_release_mode(getattr(row, "release_mode", None), default=RELEASE_TESTING)
        # Legacy / tests may only set visible_to_orgs; keep them Live until explicitly Testing.
        if mode == RELEASE_TESTING and bool(getattr(row, "visible_to_orgs", False)):
            return RELEASE_LIVE
        return mode
    @staticmethod
    def provider_enabled(db: Session, provider_key: str) -> bool:
        key = str(provider_key or "").strip().lower()
        if key == "zoho_recruit":
            from app.services.zoho_recruit_connection_service import partner_provider_enabled, platform_oauth_configured

            return bool(partner_provider_enabled(db) and platform_oauth_configured(db))
        if key == "breezy_hr":
            from app.services.breezy_hr_connection_service import partner_provider_enabled

            return bool(partner_provider_enabled(db))
        admin_key = IntegrationReleaseService._admin_provider_key(key)
        row = db.execute(
            select(ProviderConfig).where(
                ProviderConfig.scope == "platform",
                ProviderConfig.org_id.is_(None),
                ProviderConfig.provider == admin_key,
            )
        ).scalar_one_or_none()
        return bool(row is not None and row.is_enabled)

    @staticmethod
    def can_view_provider(db: Session, provider_key: str, viewer_email: str | None) -> bool:
        """
        True if the viewer may see this integration tile and its linked FAQs.
        Public/anonymous (no email): only Live + enabled.
        """
        key = str(provider_key or "").strip().lower()
        if not key:
            return True
        if not IntegrationReleaseService.provider_enabled(db, key):
            return False
        mode = IntegrationReleaseService.get_release_mode(db, key)
        if mode == RELEASE_LIVE:
            return True
        return IntegrationReleaseService.is_tester(db, viewer_email)

    @staticmethod
    def can_view_faq_item(db: Session, *, linked_provider: str | None, viewer_email: str | None) -> bool:
        link = str(linked_provider or "").strip().lower() or None
        if not link:
            return True
        return IntegrationReleaseService.can_view_provider(db, link, viewer_email)

    @staticmethod
    def apply_release_mode_to_config(obj: ProviderConfig, release_mode: str | None) -> None:
        mode = normalize_release_mode(release_mode, default=RELEASE_TESTING)
        obj.release_mode = mode
        obj.visible_to_orgs = release_mode_to_visible(mode)
