"""HubSpot static list read/write for appointments and surveys."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

HUBSPOT_LISTS_SEARCH_URL = "https://api.hubapi.com/crm/v3/lists/search"
HUBSPOT_LISTS_BASE_URL = "https://api.hubapi.com/crm/v3/lists"
HUBSPOT_CONTACTS_BATCH_READ_URL = "https://api.hubapi.com/crm/v3/objects/contacts/batch/read"
HUBSPOT_CONTACTS_SEARCH_URL = "https://api.hubapi.com/crm/v3/objects/contacts/search"

PAGE_SIZE = 100
MAX_LIST_MEMBERS = 5000
DEFAULT_APPOINTMENT_LIST_NAME = "VoxBulk · Appointments"


class HubspotListError(Exception):
    pass


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _parse_list_size(row: dict[str, Any]) -> int:
    extra = row.get("additionalProperties") if isinstance(row.get("additionalProperties"), dict) else {}
    try:
        return int(row.get("size") or extra.get("hs_list_size") or 0)
    except (TypeError, ValueError):
        return 0


def _resolve_list_size(client: httpx.Client, token: str, list_id: str, search_size: int) -> int:
    """HubSpot list search often returns size=0 briefly; fall back to detail + memberships."""
    if search_size > 0:
        return search_size
    headers = _auth_headers(token)
    detail_res = client.get(f"{HUBSPOT_LISTS_BASE_URL}/{list_id}", headers=headers)
    if detail_res.status_code < 400:
        detail_row = (detail_res.json() or {}).get("list") or {}
        if isinstance(detail_row, dict):
            detail_size = _parse_list_size(detail_row)
            if detail_size > 0:
                return detail_size
    members_res = client.get(
        f"{HUBSPOT_LISTS_BASE_URL}/{list_id}/memberships",
        headers=headers,
        params={"limit": PAGE_SIZE},
    )
    if members_res.status_code < 400:
        data = members_res.json() or {}
        results = data.get("results") or []
        return len([row for row in results if isinstance(row, dict)])
    return 0


def list_hubspot_lists(token: str, *, query: str = "", limit: int = 100) -> list[dict[str, Any]]:
    """Return MANUAL/SNAPSHOT contact lists (paginated search)."""
    lim = min(max(1, limit), 250)
    payload: dict[str, Any] = {
        "count": lim,
        "processingTypes": ["MANUAL", "SNAPSHOT"],
        "objectTypeId": "0-1",
    }
    if query.strip():
        payload["query"] = query.strip()

    items: list[dict[str, Any]] = []
    after: str | None = None
    with httpx.Client(timeout=45.0) as client:
        while len(items) < lim:
            body = dict(payload)
            if after:
                body["after"] = after
            res = client.post(HUBSPOT_LISTS_SEARCH_URL, headers=_auth_headers(token), json=body)
            if res.status_code >= 400:
                raise HubspotListError(f"HubSpot list search failed: {res.text[:300]}")
            data = res.json() or {}
            for row in data.get("lists") or []:
                if not isinstance(row, dict):
                    continue
                list_id = str(row.get("listId") or row.get("ilsListId") or "").strip()
                if not list_id:
                    continue
                items.append(
                    {
                        "id": list_id,
                        "name": str(row.get("name") or "").strip() or list_id,
                        "processing_type": str(row.get("processingType") or "").strip(),
                        "size": _parse_list_size(row),
                    }
                )
                if len(items) >= lim:
                    break
            paging = data.get("paging") or {}
            next_link = paging.get("next") if isinstance(paging, dict) else None
            after = None
            if isinstance(next_link, dict):
                after = str(next_link.get("after") or "").strip() or None
            if not after:
                break
        for item in items:
            if item.get("size", 0) > 0:
                continue
            item["size"] = _resolve_list_size(client, token, str(item["id"]), 0)
    return items


def fetch_list_member_record_ids(token: str, list_id: str, *, max_members: int = MAX_LIST_MEMBERS) -> list[str]:
    """Paginate list memberships; returns HubSpot contact record IDs."""
    lid = str(list_id or "").strip()
    if not lid:
        return []
    cap = min(max(1, max_members), MAX_LIST_MEMBERS)
    ids: list[str] = []
    after: str | None = None
    with httpx.Client(timeout=60.0) as client:
        while len(ids) < cap:
            params: dict[str, Any] = {"limit": PAGE_SIZE}
            if after:
                params["after"] = after
            res = client.get(
                f"{HUBSPOT_LISTS_BASE_URL}/{lid}/memberships",
                headers=_auth_headers(token),
                params=params,
            )
            if res.status_code >= 400:
                raise HubspotListError(f"HubSpot list memberships failed: {res.text[:300]}")
            data = res.json() or {}
            for row in data.get("results") or []:
                if not isinstance(row, dict):
                    continue
                rid = str(row.get("recordId") or row.get("vid") or "").strip()
                if rid:
                    ids.append(rid)
                    if len(ids) >= cap:
                        break
            paging = data.get("paging") or {}
            next_link = paging.get("next") if isinstance(paging, dict) else None
            after = None
            if isinstance(next_link, dict):
                after = str(next_link.get("after") or "").strip() or None
            if not after:
                break
    return ids


def batch_read_contacts(token: str, contact_ids: list[str], properties: list[str]) -> list[dict[str, Any]]:
    """Batch-read contact properties (100 IDs per HubSpot request)."""
    props = [p for p in properties if str(p).strip()]
    if not props:
        props = ["firstname", "lastname", "email", "phone"]
    unique_ids = [str(x).strip() for x in contact_ids if str(x).strip()]
    if not unique_ids:
        return []

    out: list[dict[str, Any]] = []
    with httpx.Client(timeout=60.0) as client:
        for i in range(0, len(unique_ids), PAGE_SIZE):
            chunk = unique_ids[i : i + PAGE_SIZE]
            payload = {
                "properties": props,
                "inputs": [{"id": cid} for cid in chunk],
            }
            res = client.post(
                HUBSPOT_CONTACTS_BATCH_READ_URL,
                headers=_auth_headers(token),
                json=payload,
            )
            if res.status_code >= 400:
                raise HubspotListError(f"HubSpot contact batch read failed: {res.text[:300]}")
            body = res.json() or {}
            for item in body.get("results") or []:
                if isinstance(item, dict):
                    out.append(item)
    return out


def create_hubspot_static_list(token: str, name: str) -> str:
    list_name = str(name or "").strip() or DEFAULT_APPOINTMENT_LIST_NAME
    with httpx.Client(timeout=30.0) as client:
        res = client.post(
            HUBSPOT_LISTS_BASE_URL,
            headers=_auth_headers(token),
            json={"name": list_name, "objectTypeId": "0-1", "processingType": "MANUAL"},
        )
    if res.status_code >= 400:
        raise HubspotListError(f"HubSpot list create failed: {res.text[:300]}")
    list_id = str((res.json() or {}).get("list", {}).get("listId") or "").strip()
    if not list_id:
        raise HubspotListError("HubSpot list create returned no listId")
    return list_id


def find_hubspot_list_id_by_name(token: str, name: str) -> str | None:
    target = str(name or "").strip().lower()
    if not target:
        return None
    for row in list_hubspot_lists(token, query=name, limit=50):
        if str(row.get("name") or "").strip().lower() == target:
            return str(row.get("id") or "").strip() or None
    return None


def ensure_appointment_source_list(token: str, list_id: str | None, *, default_name: str = DEFAULT_APPOINTMENT_LIST_NAME) -> str:
    """Return configured list id, or find/create the default static appointment list."""
    configured = str(list_id or "").strip()
    if configured:
        return configured
    existing = find_hubspot_list_id_by_name(token, default_name)
    if existing:
        return existing
    return create_hubspot_static_list(token, default_name)


def search_contacts_with_appointment_date(
    token: str,
    date_prop: str,
    properties: list[str],
    *,
    max_results: int = MAX_LIST_MEMBERS,
) -> list[dict[str, Any]]:
    """HubSpot contacts that have both phone and the appointment date property set."""
    date_field = str(date_prop or "appointment_date").strip() or "appointment_date"
    props = list(dict.fromkeys([*properties, "phone", date_field]))
    cap = min(max(1, max_results), MAX_LIST_MEMBERS)
    out: list[dict[str, Any]] = []
    after: str | None = None
    with httpx.Client(timeout=60.0) as client:
        while len(out) < cap:
            payload: dict[str, Any] = {
                "filterGroups": [
                    {
                        "filters": [
                            {"propertyName": "phone", "operator": "HAS_PROPERTY"},
                            {"propertyName": date_field, "operator": "HAS_PROPERTY"},
                        ]
                    }
                ],
                "properties": props,
                "limit": min(PAGE_SIZE, cap - len(out)),
            }
            if after:
                payload["after"] = after
            res = client.post(HUBSPOT_CONTACTS_SEARCH_URL, headers=_auth_headers(token), json=payload)
            if res.status_code >= 400:
                raise HubspotListError(f"HubSpot contact search failed: {res.text[:300]}")
            body = res.json() or {}
            for item in body.get("results") or []:
                if isinstance(item, dict):
                    out.append(item)
                    if len(out) >= cap:
                        break
            paging = body.get("paging") or {}
            next_link = paging.get("next") if isinstance(paging, dict) else None
            after = None
            if isinstance(next_link, dict):
                after = str(next_link.get("after") or "").strip() or None
            if not after:
                break
    return out


def sync_contacts_to_list(token: str, list_id: str, record_ids: list[str]) -> int:
    """Add contacts to a static list (ignored if already members). Returns count attempted."""
    ids = [str(x).strip() for x in record_ids if str(x).strip()]
    lid = str(list_id or "").strip()
    if not ids or not lid:
        return 0
    for i in range(0, len(ids), PAGE_SIZE):
        chunk = ids[i : i + PAGE_SIZE]
        with httpx.Client(timeout=30.0) as client:
            res = client.put(
                f"{HUBSPOT_LISTS_BASE_URL}/{lid}/memberships/add",
                headers=_auth_headers(token),
                json=chunk,
            )
        if res.status_code >= 400:
            raise HubspotListError(f"HubSpot add to list failed: {res.text[:300]}")
    return len(ids)


def add_contacts_to_list(token: str, list_id: str, record_ids: list[str]) -> None:
    sync_contacts_to_list(token, list_id, record_ids)


def remove_contacts_from_list(token: str, list_id: str, record_ids: list[str]) -> None:
    ids = [str(x).strip() for x in record_ids if str(x).strip()]
    if not ids or not str(list_id or "").strip():
        return
    with httpx.Client(timeout=30.0) as client:
        res = client.put(
            f"{HUBSPOT_LISTS_BASE_URL}/{list_id.strip()}/memberships/remove",
            headers=_auth_headers(token),
            json=ids,
        )
    if res.status_code >= 400:
        raise HubspotListError(f"HubSpot remove from list failed: {res.text[:300]}")


def move_contact_between_lists(
    token: str,
    *,
    contact_id: str,
    remove_from_list_id: str | None,
    add_to_list_id: str | None,
) -> None:
    """Remove from source list and add to target list (best-effort)."""
    cid = str(contact_id or "").strip()
    if not cid:
        return
    remove_id = str(remove_from_list_id or "").strip() or None
    add_id = str(add_to_list_id or "").strip() or None
    if remove_id:
        try:
            remove_contacts_from_list(token, remove_id, [cid])
        except HubspotListError as exc:
            logger.warning("hubspot_list_remove_failed list=%s contact=%s err=%s", remove_id, cid, str(exc)[:120])
    if add_id:
        try:
            add_contacts_to_list(token, add_id, [cid])
        except HubspotListError as exc:
            logger.warning("hubspot_list_add_failed list=%s contact=%s err=%s", add_id, cid, str(exc)[:120])


def fetch_list_contacts(
    token: str,
    list_id: str,
    properties: list[str],
    *,
    max_members: int = MAX_LIST_MEMBERS,
) -> list[dict[str, Any]]:
    """List member contact records with requested properties."""
    record_ids = fetch_list_member_record_ids(token, list_id, max_members=max_members)
    if not record_ids:
        return []
    return batch_read_contacts(token, record_ids, properties)
