"""Dispatch interview CRM sync to the single active CRM provider."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.crm_connection_service import active_crm_provider


def _crm_status(db: Session, org_id: str, provider: str) -> dict[str, Any]:
    if provider == "hubspot":
        from app.services.hubspot_connection_service import hubspot_status

        return hubspot_status(db, org_id)
    if provider == "pipedrive":
        from app.services.pipedrive_connection_service import pipedrive_status

        return pipedrive_status(db, org_id)
    if provider == "zoho_crm":
        from app.services.zoho_crm_connection_service import zoho_crm_status

        return zoho_crm_status(db, org_id)
    return {"connected": False}


def sync_shortlist_to_active_crm(
    db: Session,
    org_id: str,
    *,
    order: ServiceOrder,
    recipient_ids: list[str],
) -> dict[str, Any]:
    provider = active_crm_provider(db, org_id)
    if not provider:
        return {"ok": True, "synced": 0, "skipped": True, "provider": None}
    if provider == "hubspot":
        from app.services.hubspot_connection_service import sync_shortlist_to_hubspot

        result = sync_shortlist_to_hubspot(db, org_id, order=order, recipient_ids=recipient_ids)
    elif provider == "pipedrive":
        from app.services.pipedrive_connection_service import sync_shortlist_to_pipedrive

        result = sync_shortlist_to_pipedrive(db, org_id, order=order, recipient_ids=recipient_ids)
    elif provider == "zoho_crm":
        from app.services.zoho_crm_connection_service import sync_shortlist_to_zoho_crm

        result = sync_shortlist_to_zoho_crm(db, org_id, order=order, recipient_ids=recipient_ids)
    else:
        return {"ok": True, "synced": 0, "skipped": True, "provider": provider}
    result["provider"] = provider
    return result


def sync_recipient_to_active_crm(
    db: Session,
    org_id: str,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    scheduling_url: str = "",
) -> dict[str, Any]:
    provider = active_crm_provider(db, org_id)
    if not provider:
        raise ValueError("No CRM connected")
    status = _crm_status(db, org_id, provider)
    if not status.get("connected"):
        raise ValueError("CRM is not connected")
    if not status.get("auto_sync_scheduling_send", True):
        return {"ok": True, "skipped": True, "provider": provider}

    if provider == "hubspot":
        from app.services.hubspot_connection_service import sync_recipient_to_hubspot

        result = sync_recipient_to_hubspot(
            db, org_id, order=order, recipient=recipient, scheduling_url=scheduling_url
        )
    elif provider == "pipedrive":
        from app.services.pipedrive_connection_service import sync_recipient_to_pipedrive

        result = sync_recipient_to_pipedrive(
            db, org_id, order=order, recipient=recipient, scheduling_url=scheduling_url
        )
    elif provider == "zoho_crm":
        from app.services.zoho_crm_connection_service import sync_recipient_to_zoho_crm

        result = sync_recipient_to_zoho_crm(
            db, org_id, order=order, recipient=recipient, scheduling_url=scheduling_url
        )
    else:
        raise ValueError(f"Unsupported CRM provider: {provider}")
    result["provider"] = provider
    return result


def active_crm_auto_sync_scheduling_enabled(db: Session, org_id: str) -> bool:
    provider = active_crm_provider(db, org_id)
    if not provider:
        return False
    status = _crm_status(db, org_id, provider)
    return bool(status.get("connected") and status.get("auto_sync_scheduling_send", True))
