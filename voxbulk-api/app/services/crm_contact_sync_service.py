"""Unified CRM contact sync facade (HubSpot, Pipedrive, Zoho CRM)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.crm_connection_service import active_crm_provider


class CrmContactSyncError(Exception):
    pass


def _require_active_provider(db: Session, org_id: str) -> str:
    provider = active_crm_provider(db, org_id)
    if not provider:
        raise CrmContactSyncError("Connect a CRM in Settings → Integrations first")
    return provider


def crm_sync_status(db: Session, org_id: str) -> dict[str, Any]:
    provider = active_crm_provider(db, org_id)
    if not provider:
        return {
            "ok": True,
            "provider": None,
            "connected": False,
            "sync_settings_enabled": False,
            "contact_count": 0,
        }

    if provider == "hubspot":
        from app.services.hubspot_connection_service import get_hubspot_config, hubspot_status
        from app.services.hubspot_contact_sync_service import is_sync_v1_enabled, sync_status_extras

        status = hubspot_status(db, org_id)
        cfg = get_hubspot_config(db, org_id)
        extras = sync_status_extras(db, org_id, cfg)
        return {
            "ok": True,
            "provider": provider,
            "connected": status.get("connected") is True,
            "sync_settings_enabled": is_sync_v1_enabled(db) and status.get("connected") is True,
            **extras,
        }

    if provider == "pipedrive":
        from app.services.pipedrive_connection_service import get_pipedrive_config, pipedrive_status
        from app.services.pipedrive_contact_sync_service import sync_status_extras

        status = pipedrive_status(db, org_id)
        cfg = get_pipedrive_config(db, org_id)
        extras = sync_status_extras(db, org_id, cfg)
        return {
            "ok": True,
            "provider": provider,
            "connected": status.get("connected") is True,
            **extras,
        }

    if provider == "zoho_crm":
        from app.services.zoho_crm_connection_service import get_zoho_crm_config, zoho_crm_status
        from app.services.zoho_crm_contact_sync_service import sync_status_extras

        status = zoho_crm_status(db, org_id)
        cfg = get_zoho_crm_config(db, org_id)
        extras = sync_status_extras(db, org_id, cfg)
        return {
            "ok": True,
            "provider": provider,
            "connected": status.get("connected") is True,
            **extras,
        }

    return {"ok": True, "provider": provider, "connected": False, "sync_settings_enabled": False}


def sync_contacts(db: Session, org_id: str, *, limit: int = 100) -> dict[str, Any]:
    provider = _require_active_provider(db, org_id)

    if provider == "hubspot":
        from app.services.hubspot_contact_sync_service import HubspotContactSyncError, fetch_and_upsert_contacts

        try:
            result = fetch_and_upsert_contacts(db, org_id, limit=limit)
            result["provider"] = provider
            return result
        except HubspotContactSyncError as exc:
            raise CrmContactSyncError(str(exc)) from exc

    if provider == "pipedrive":
        from app.services.pipedrive_contact_sync_service import PipedriveContactSyncError, fetch_and_upsert_contacts

        try:
            result = fetch_and_upsert_contacts(db, org_id, limit=limit)
            return result
        except PipedriveContactSyncError as exc:
            raise CrmContactSyncError(str(exc)) from exc

    if provider == "zoho_crm":
        from app.services.zoho_crm_contact_sync_service import ZohoCrmContactSyncError, fetch_and_upsert_contacts

        try:
            result = fetch_and_upsert_contacts(db, org_id, limit=limit)
            return result
        except ZohoCrmContactSyncError as exc:
            raise CrmContactSyncError(str(exc)) from exc

    raise CrmContactSyncError(f"Contact sync is not supported for {provider}")


def list_contacts(db: Session, org_id: str, *, limit: int = 50) -> dict[str, Any]:
    provider = _require_active_provider(db, org_id)

    if provider == "hubspot":
        from app.services.hubspot_contact_sync_service import HubspotContactSyncError, list_contacts as hs_list

        try:
            result = hs_list(db, org_id, limit=limit)
            items = [
                {
                    "id": row["id"],
                    "external_id": row.get("hubspot_contact_id"),
                    "name": row.get("name"),
                    "email": row.get("email"),
                    "phone": row.get("phone"),
                    "synced_at": row.get("synced_at"),
                }
                for row in result.get("items") or []
            ]
            return {"ok": True, "provider": provider, "items": items, "count": len(items)}
        except HubspotContactSyncError as exc:
            raise CrmContactSyncError(str(exc)) from exc

    if provider == "pipedrive":
        from app.services.pipedrive_contact_sync_service import PipedriveContactSyncError, list_contacts as pd_list

        try:
            return pd_list(db, org_id, limit=limit)
        except PipedriveContactSyncError as exc:
            raise CrmContactSyncError(str(exc)) from exc

    if provider == "zoho_crm":
        from app.services.zoho_crm_contact_sync_service import ZohoCrmContactSyncError, list_contacts as zoho_list

        try:
            return zoho_list(db, org_id, limit=limit)
        except ZohoCrmContactSyncError as exc:
            raise CrmContactSyncError(str(exc)) from exc

    raise CrmContactSyncError(f"Contact list is not supported for {provider}")


def import_contacts_to_order(
    db: Session,
    org_id: str,
    *,
    order_id: str,
    contact_ids: list[str],
) -> dict[str, Any]:
    provider = _require_active_provider(db, org_id)

    if provider == "hubspot":
        from app.services.hubspot_contact_sync_service import HubspotContactSyncError, import_contacts_to_order as hs_import

        try:
            result = hs_import(db, org_id, order_id=order_id, contact_ids=contact_ids)
            result["provider"] = provider
            return result
        except HubspotContactSyncError as exc:
            raise CrmContactSyncError(str(exc)) from exc

    if provider == "pipedrive":
        from app.services.pipedrive_contact_sync_service import PipedriveContactSyncError, import_contacts_to_order as pd_import

        try:
            return pd_import(db, org_id, order_id=order_id, contact_ids=contact_ids)
        except PipedriveContactSyncError as exc:
            raise CrmContactSyncError(str(exc)) from exc

    if provider == "zoho_crm":
        from app.services.zoho_crm_contact_sync_service import ZohoCrmContactSyncError, import_contacts_to_order as zoho_import

        try:
            return zoho_import(db, org_id, order_id=order_id, contact_ids=contact_ids)
        except ZohoCrmContactSyncError as exc:
            raise CrmContactSyncError(str(exc)) from exc

    raise CrmContactSyncError(f"CRM import is not supported for {provider}")


def import_list_contacts_to_order(
    db: Session,
    org_id: str,
    *,
    order_id: str,
    list_id: str | None = None,
) -> dict[str, Any]:
    provider = _require_active_provider(db, org_id)
    if provider != "hubspot":
        raise CrmContactSyncError("HubSpot list import requires HubSpot as the active CRM")

    from app.services.hubspot_contact_sync_service import HubspotContactSyncError, import_list_contacts_to_order as hs_import

    try:
        result = hs_import(db, org_id, order_id=order_id, list_id=list_id)
        result["provider"] = provider
        return result
    except HubspotContactSyncError as exc:
        raise CrmContactSyncError(str(exc)) from exc


def list_hubspot_lists_for_org(db: Session, org_id: str, *, query: str = "", limit: int = 100) -> dict[str, Any]:
    from app.services.hubspot_connection_service import _ensure_access_token, hubspot_status
    from app.services.hubspot_list_service import HubspotListError, list_hubspot_lists

    if not hubspot_status(db, org_id).get("connected"):
        raise CrmContactSyncError("Connect HubSpot first")
    token = _ensure_access_token(db, org_id)
    if not token:
        raise CrmContactSyncError("Connect HubSpot first")
    try:
        items = list_hubspot_lists(token, query=query, limit=limit)
    except HubspotListError as exc:
        raise CrmContactSyncError(str(exc)) from exc
    return {"ok": True, "provider": "hubspot", "items": items, "count": len(items)}


def update_crm_sync_settings(
    db: Session,
    org_id: str,
    *,
    auto_sync_results_back: bool | None = None,
    field_map: dict[str, str] | None = None,
    appointment_list_id: str | None = None,
    survey_list_id: str | None = None,
    appointment_confirmed_list_id: str | None = None,
    appointment_cancelled_list_id: str | None = None,
) -> dict[str, Any]:
    provider = _require_active_provider(db, org_id)

    if provider == "hubspot":
        from app.services.hubspot_contact_sync_service import HubspotContactSyncError, update_hubspot_sync_settings

        try:
            return update_hubspot_sync_settings(
                db,
                org_id,
                field_map=field_map,
                auto_sync_results_back=auto_sync_results_back,
                appointment_list_id=appointment_list_id,
                survey_list_id=survey_list_id,
                appointment_confirmed_list_id=appointment_confirmed_list_id,
                appointment_cancelled_list_id=appointment_cancelled_list_id,
            )
        except HubspotContactSyncError as exc:
            raise CrmContactSyncError(str(exc)) from exc

    if provider == "pipedrive":
        from app.services.pipedrive_connection_service import update_pipedrive_settings

        return update_pipedrive_settings(db, org_id, auto_sync_results_back=auto_sync_results_back)

    if provider == "zoho_crm":
        from app.services.zoho_crm_connection_service import update_zoho_crm_settings

        return update_zoho_crm_settings(db, org_id, auto_sync_results_back=auto_sync_results_back)

    raise CrmContactSyncError(f"Sync settings are not supported for {provider}")
