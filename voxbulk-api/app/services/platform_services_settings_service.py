"""Platform default allowed dashboard modules (VoxBulk-wide)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.platform_services_settings import PlatformServicesSettings
from app.services.org_enabled_services import (
    AtLeastOneServiceRequiredError,
    DEFAULT_ENABLED_SERVICES,
    merge_admin_allowed_services,
    org_service_maps,
    parse_allowed_services,
    parse_enabled_services,
    serialize_allowed_services,
    serialize_enabled_services,
)


def get_platform_default_allowed(db: Session) -> dict[str, bool]:
    row = ensure_row(db)
    return parse_allowed_services(row.default_allowed_services_json, platform_default=None)


def ensure_row(db: Session) -> PlatformServicesSettings:
    row = db.get(PlatformServicesSettings, "default")
    if row is None:
        row = PlatformServicesSettings(
            id="default",
            default_allowed_services_json=serialize_allowed_services(DEFAULT_ENABLED_SERVICES),
            updated_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def update_platform_default_allowed(db: Session, patch: dict[str, Any] | None) -> dict[str, bool]:
    row = ensure_row(db)
    current = parse_allowed_services(row.default_allowed_services_json, platform_default=None)
    merged = dict(current)
    if isinstance(patch, dict):
        for key in DEFAULT_ENABLED_SERVICES:
            if key in patch:
                merged[key] = bool(patch[key])
    if not any(merged.values()):
        raise AtLeastOneServiceRequiredError(
            "At least one dashboard service must remain enabled in platform defaults."
        )
    row.default_allowed_services_json = serialize_allowed_services(merged)
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return parse_allowed_services(row.default_allowed_services_json, platform_default=None)


def push_platform_default_to_orgs(
    db: Session,
    *,
    org_ids: list[str] | None = None,
    clear_overrides_only: bool = False,
) -> int:
    """Apply platform defaults to orgs. Returns count updated."""
    platform_allowed = get_platform_default_allowed(db)
    q = select(Organisation)
    if org_ids:
        q = q.where(Organisation.id.in_(org_ids))
    orgs = list(db.execute(q).scalars().all())
    updated = 0
    for org in orgs:
        if clear_overrides_only:
            org.allowed_services_json = None
        else:
            _, enabled, _ = org_service_maps(org, db)
            allowed, enabled = merge_admin_allowed_services(platform_allowed, enabled, None)
            org.allowed_services_json = serialize_allowed_services(allowed)
            org.enabled_services_json = serialize_enabled_services(enabled)
        db.add(org)
        updated += 1
    if updated:
        db.commit()
    return updated


def bulk_patch_org_allowed_services(
    db: Session,
    *,
    org_ids: list[str] | None,
    services_patch: dict[str, Any] | None,
    reset_to_platform_default: bool = False,
) -> int:
    if not org_ids and not reset_to_platform_default and not services_patch:
        return 0
    q = select(Organisation)
    if org_ids:
        q = q.where(Organisation.id.in_(org_ids))
    orgs = list(db.execute(q).scalars().all())
    updated = 0
    for org in orgs:
        if reset_to_platform_default:
            org.allowed_services_json = None
            _, enabled, _ = org_service_maps(org, db)
            org.enabled_services_json = serialize_enabled_services(enabled)
        elif services_patch:
            _, enabled, _ = org_service_maps(org, db)
            from app.services.org_enabled_services import apply_admin_org_service_grants

            allowed, enabled = apply_admin_org_service_grants(enabled, services_patch)
            org.allowed_services_json = serialize_allowed_services(allowed)
            org.enabled_services_json = serialize_enabled_services(enabled)
        else:
            continue
        db.add(org)
        updated += 1
    if updated:
        db.commit()
    return updated
