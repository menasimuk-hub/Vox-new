"""Zoho CRM contact pull, import to surveys, and survey result write-back."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.crm_synced_contact import CrmSyncedContact
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.crm_connection_service import save_crm_config_raw
from app.services.crm_survey_result_format import survey_result_summary
from app.services.messaging_log_service import normalize_e164
from app.services.zoho_crm_connection_service import (
    _ensure_access_token,
    _search_contact_by_email,
    get_zoho_crm_config,
    zoho_crm_status,
)

logger = logging.getLogger(__name__)
DEFAULT_SYNC_LIMIT = 100
PROVIDER = "zoho_crm"


class ZohoCrmContactSyncError(Exception):
    pass


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _zoho_api_base(api_domain: str) -> str:
    domain = str(api_domain or "").strip().rstrip("/")
    if not domain:
        return "https://www.zohoapis.com"
    if domain.startswith("http"):
        return domain.rstrip("/")
    return f"https://{domain}"


def sync_status_extras(db: Session, org_id: str, cfg: dict[str, Any]) -> dict[str, Any]:
    count = int(
        db.execute(
            select(func.count())
            .select_from(CrmSyncedContact)
            .where(CrmSyncedContact.org_id == org_id, CrmSyncedContact.provider == PROVIDER)
        ).scalar_one()
        or 0
    )
    return {
        "sync_settings_enabled": zoho_crm_status(db, org_id).get("connected") is True,
        "auto_sync_results_back": cfg.get("auto_sync_results_back") is not False,
        "last_sync_at": cfg.get("last_sync_at"),
        "contact_count": count,
        "last_sync_summary": cfg.get("last_sync_summary"),
    }


def _map_contact(row: dict[str, Any]) -> dict[str, str | None]:
    first = str(row.get("First_Name") or row.get("first_name") or "").strip()
    last = str(row.get("Last_Name") or row.get("last_name") or "").strip()
    name = " ".join(p for p in (first, last) if p).strip()
    email = str(row.get("Email") or row.get("email") or "").strip() or None
    phone_raw = str(row.get("Phone") or row.get("Mobile") or row.get("phone") or "").strip()
    phone: str | None = None
    if phone_raw:
        try:
            phone = normalize_e164(phone_raw)
        except ValueError:
            phone = None
    return {"name": name or email or "Contact", "email": email, "phone": phone}


def fetch_and_upsert_contacts(db: Session, org_id: str, *, limit: int = DEFAULT_SYNC_LIMIT) -> dict[str, Any]:
    status = zoho_crm_status(db, org_id)
    if not status.get("connected"):
        raise ZohoCrmContactSyncError("Connect Zoho CRM before syncing contacts")

    cfg = get_zoho_crm_config(db, org_id)
    token, api_domain = _ensure_access_token(db, org_id)
    base = _zoho_api_base(api_domain)
    lim = min(max(1, limit), DEFAULT_SYNC_LIMIT)
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}

    with httpx.Client(timeout=45.0) as client:
        res = client.get(
            f"{base}/crm/v2/Contacts",
            headers=headers,
            params={
                "fields": "First_Name,Last_Name,Email,Phone,Mobile",
                "per_page": lim,
                "page": 1,
            },
        )

    if res.status_code >= 400:
        raise ZohoCrmContactSyncError(f"Zoho CRM contact fetch failed: {res.text[:300]}")

    body = res.json() or {}
    results = body.get("data") or []
    info = body.get("info") or {}
    has_more = bool(info.get("more_records"))

    imported = 0
    updated = 0
    skipped = 0
    now = datetime.utcnow()

    for item in results:
        if not isinstance(item, dict):
            skipped += 1
            continue
        ext_id = str(item.get("id") or "").strip()
        if not ext_id:
            skipped += 1
            continue
        mapped = _map_contact(item)
        if not mapped.get("email") and not mapped.get("phone"):
            skipped += 1
            continue

        existing = db.execute(
            select(CrmSyncedContact).where(
                CrmSyncedContact.org_id == org_id,
                CrmSyncedContact.provider == PROVIDER,
                CrmSyncedContact.external_contact_id == ext_id,
            )
        ).scalar_one_or_none()

        if existing is None:
            db.add(
                CrmSyncedContact(
                    id=str(uuid.uuid4()),
                    org_id=org_id,
                    provider=PROVIDER,
                    external_contact_id=ext_id,
                    name=str(mapped["name"] or "Contact"),
                    email=mapped.get("email"),
                    phone=mapped.get("phone"),
                    raw_properties_json=json.dumps(item, ensure_ascii=False),
                    synced_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
            imported += 1
        else:
            existing.name = str(mapped["name"] or existing.name or "Contact")
            existing.email = mapped.get("email") or existing.email
            existing.phone = mapped.get("phone") or existing.phone
            existing.raw_properties_json = json.dumps(item, ensure_ascii=False)
            existing.synced_at = now
            existing.updated_at = now
            db.add(existing)
            updated += 1

    summary = {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "fetched": len(results),
        "has_more": has_more,
    }
    cfg_update = dict(cfg)
    cfg_update["last_sync_at"] = now.isoformat()
    cfg_update["last_sync_summary"] = summary
    save_crm_config_raw(db, org_id, PROVIDER, cfg_update)
    db.commit()
    return {"ok": True, **summary, "message": f"Synced {imported + updated} contact(s) from Zoho CRM"}


def list_contacts(db: Session, org_id: str, *, limit: int = 50) -> dict[str, Any]:
    lim = min(max(1, limit), 100)
    rows = list(
        db.execute(
            select(CrmSyncedContact)
            .where(CrmSyncedContact.org_id == org_id, CrmSyncedContact.provider == PROVIDER)
            .order_by(CrmSyncedContact.synced_at.desc())
            .limit(lim)
        ).scalars().all()
    )
    return {
        "ok": True,
        "provider": PROVIDER,
        "items": [
            {
                "id": r.id,
                "external_id": r.external_contact_id,
                "name": r.name,
                "email": r.email,
                "phone": r.phone,
                "synced_at": r.synced_at.isoformat() if r.synced_at else None,
            }
            for r in rows
        ],
        "count": len(rows),
    }


def _normalize_phone_loose(raw: str | None) -> str:
    if not raw:
        return ""
    return "".join(ch for ch in str(raw) if ch.isdigit())


def _recipient_exists(recipients: list[ServiceOrderRecipient], *, email: str | None, phone: str | None) -> bool:
    email_key = str(email or "").strip().lower()
    phone_key = _normalize_phone_loose(phone)
    for r in recipients:
        if email_key and str(r.email or "").strip().lower() == email_key:
            return True
        if phone_key and _normalize_phone_loose(r.phone) == phone_key:
            return True
    return False


def import_contacts_to_order(
    db: Session,
    org_id: str,
    *,
    order_id: str,
    contact_ids: list[str],
) -> dict[str, Any]:
    from app.services.platform_catalog_service import ServiceOrderService

    order = ServiceOrderService.get_order(db, order_id, org_id=org_id)
    if order is None:
        raise ZohoCrmContactSyncError("Order not found")
    if order.service_code != "survey":
        raise ZohoCrmContactSyncError("CRM import is only supported for survey campaigns")
    if order.status == "completed":
        raise ZohoCrmContactSyncError("Cannot import contacts into a completed campaign")
    if str(order.payment_status or "").lower() == "approved":
        raise ZohoCrmContactSyncError("Cannot import contacts after payment is approved")

    id_set = {str(x).strip() for x in contact_ids if str(x).strip()}
    if not id_set:
        raise ZohoCrmContactSyncError("Select at least one contact")

    contacts = list(
        db.execute(
            select(CrmSyncedContact).where(
                CrmSyncedContact.org_id == org_id,
                CrmSyncedContact.provider == PROVIDER,
                CrmSyncedContact.id.in_(id_set),
            )
        ).scalars().all()
    )
    if not contacts:
        raise ZohoCrmContactSyncError("No matching synced contacts found")

    recipients = list(
        db.execute(select(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id)).scalars().all()
    )
    added = 0
    skipped = 0
    for contact in contacts:
        if not contact.phone:
            skipped += 1
            continue
        if _recipient_exists(recipients, email=contact.email, phone=contact.phone):
            skipped += 1
            continue
        recipient = ServiceOrderRecipient(
            order_id=order.id,
            row_number=len(recipients) + 1,
            name=contact.name or "Contact",
            phone=contact.phone,
            email=contact.email,
            status="pending",
        )
        db.add(recipient)
        recipients.append(recipient)
        added += 1

    for i, r in enumerate(recipients, start=1):
        r.row_number = i
        db.add(r)
    order.recipient_count = len(recipients)
    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()
    db.refresh(order)
    return {
        "ok": True,
        "added": added,
        "skipped": skipped,
        "recipient_count": order.recipient_count,
        "order_id": order.id,
    }


def sync_survey_result_to_zoho_crm(
    db: Session,
    org_id: str,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    force: bool = False,
) -> dict[str, Any]:
    status = zoho_crm_status(db, org_id)
    if not status.get("connected"):
        if force:
            raise ZohoCrmContactSyncError("Connect Zoho CRM before pushing survey results")
        return {"ok": True, "skipped": True, "reason": "not_connected"}

    cfg = get_zoho_crm_config(db, org_id)
    if not force and cfg.get("auto_sync_results_back") is False:
        return {"ok": True, "skipped": True, "reason": "auto_sync_disabled"}

    email = str(recipient.email or "").strip()
    phone = str(recipient.phone or "").strip()
    if not email and not phone:
        if force:
            raise ZohoCrmContactSyncError("Respondent needs email or phone to match a Zoho contact")
        return {"ok": True, "skipped": True, "reason": "no_email_or_phone"}

    token, api_domain = _ensure_access_token(db, org_id)
    base = _zoho_api_base(api_domain)
    contact_id = _search_contact_by_email(token, api_domain, email) if email else None
    if not contact_id and phone:
        pool = db.execute(
            select(CrmSyncedContact).where(
                CrmSyncedContact.org_id == org_id,
                CrmSyncedContact.provider == PROVIDER,
                CrmSyncedContact.phone == phone,
            ).limit(1)
        ).scalar_one_or_none()
        if pool:
            contact_id = pool.external_contact_id
    if not contact_id:
        merged = _loads(recipient.result_json)
        contact_id = str(merged.get("zoho_crm_contact_id") or "").strip() or None
    if not contact_id:
        if force:
            raise ZohoCrmContactSyncError("No matching Zoho CRM contact found for this respondent")
        return {"ok": True, "skipped": True, "reason": "contact_not_found"}

    note_title = f"VoxBulk survey — {order.title or 'Survey'}"[:120]
    note_body = survey_result_summary(order, recipient)
    headers = {"Authorization": f"Zoho-oauthtoken {token}", "Content-Type": "application/json"}
    payload = {
        "data": [
            {
                "Note_Title": note_title,
                "Note_Content": note_body,
                "Parent_Id": contact_id,
                "$se_module": "Contacts",
            }
        ]
    }
    with httpx.Client(timeout=30.0) as client:
        res = client.post(f"{base}/crm/v2/Notes", headers=headers, json=payload)
    if res.status_code >= 400:
        raise ZohoCrmContactSyncError(f"Zoho CRM note create failed: {res.text[:300]}")

    merged = _loads(recipient.result_json)
    merged.update(
        {
            "zoho_crm_contact_id": contact_id,
            "zoho_crm_synced_at": datetime.utcnow().isoformat(),
            "zoho_crm_sync_note": note_body.split("\n", 1)[0],
        }
    )
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    db.add(recipient)

    return {
        "ok": True,
        "provider": PROVIDER,
        "contact_id": contact_id,
        "note_created": True,
    }
