"""Pipedrive contact pull, import to surveys, and survey result write-back."""

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
from app.services.crm_survey_result_format import survey_result_summary
from app.services.messaging_log_service import normalize_e164
from app.services.crm_connection_service import save_crm_config_raw
from app.services.pipedrive_connection_service import (
    PIPEDRIVE_API_BASE,
    _ensure_access_token,
    _search_person_by_email,
    get_pipedrive_config,
    pipedrive_status,
)

logger = logging.getLogger(__name__)
DEFAULT_SYNC_LIMIT = 100
PROVIDER = "pipedrive"


class PipedriveContactSyncError(Exception):
    pass


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


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
        "sync_settings_enabled": pipedrive_status(db, org_id).get("connected") is True,
        "auto_sync_results_back": cfg.get("auto_sync_results_back") is not False,
        "last_sync_at": cfg.get("last_sync_at"),
        "contact_count": count,
        "last_sync_summary": cfg.get("last_sync_summary"),
    }


def _primary_value(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    for row in items:
        if isinstance(row, dict) and row.get("primary"):
            return str(row.get("value") or "").strip()
    if items and isinstance(items[0], dict):
        return str(items[0].get("value") or "").strip()
    return ""


def _map_person(person: dict[str, Any]) -> dict[str, str | None]:
    name = str(person.get("name") or "").strip()
    email = _primary_value(person.get("email")) or None
    phone_raw = _primary_value(person.get("phone"))
    phone: str | None = None
    if phone_raw:
        try:
            phone = normalize_e164(phone_raw)
        except ValueError:
            phone = None
    return {"name": name or email or "Contact", "email": email, "phone": phone}


def fetch_and_upsert_contacts(db: Session, org_id: str, *, limit: int = DEFAULT_SYNC_LIMIT) -> dict[str, Any]:
    status = pipedrive_status(db, org_id)
    if not status.get("connected"):
        raise PipedriveContactSyncError("Connect Pipedrive before syncing contacts")

    cfg = get_pipedrive_config(db, org_id)
    token = _ensure_access_token(db, org_id)
    lim = min(max(1, limit), DEFAULT_SYNC_LIMIT)
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(timeout=45.0) as client:
        res = client.get(f"{PIPEDRIVE_API_BASE}/persons", headers=headers, params={"limit": lim, "start": 0})

    if res.status_code >= 400:
        raise PipedriveContactSyncError(f"Pipedrive contact fetch failed: {res.text[:300]}")

    body = res.json() or {}
    results = body.get("data") or []
    pagination = body.get("additional_data", {}).get("pagination") or {}
    has_more = bool(pagination.get("more_items_in_collection"))

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
        mapped = _map_person(item)
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
    return {"ok": True, **summary, "message": f"Synced {imported + updated} contact(s) from Pipedrive"}


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
        raise PipedriveContactSyncError("Order not found")
    if order.service_code != "survey":
        raise PipedriveContactSyncError("CRM import is only supported for survey campaigns")
    if order.status == "completed":
        raise PipedriveContactSyncError("Cannot import contacts into a completed campaign")
    if str(order.payment_status or "").lower() == "approved":
        raise PipedriveContactSyncError("Cannot import contacts after payment is approved")

    id_set = {str(x).strip() for x in contact_ids if str(x).strip()}
    if not id_set:
        raise PipedriveContactSyncError("Select at least one contact")

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
        raise PipedriveContactSyncError("No matching synced contacts found")

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


def sync_survey_result_to_pipedrive(
    db: Session,
    org_id: str,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    force: bool = False,
) -> dict[str, Any]:
    status = pipedrive_status(db, org_id)
    if not status.get("connected"):
        if force:
            raise PipedriveContactSyncError("Connect Pipedrive before pushing survey results")
        return {"ok": True, "skipped": True, "reason": "not_connected"}

    cfg = get_pipedrive_config(db, org_id)
    if not force and cfg.get("auto_sync_results_back") is False:
        return {"ok": True, "skipped": True, "reason": "auto_sync_disabled"}

    email = str(recipient.email or "").strip()
    phone = str(recipient.phone or "").strip()
    if not email and not phone:
        if force:
            raise PipedriveContactSyncError("Respondent needs email or phone to match a Pipedrive person")
        return {"ok": True, "skipped": True, "reason": "no_email_or_phone"}

    token = _ensure_access_token(db, org_id)
    person_id = _search_person_by_email(token, email) if email else None
    if not person_id:
        pool = db.execute(
            select(CrmSyncedContact).where(
                CrmSyncedContact.org_id == org_id,
                CrmSyncedContact.provider == PROVIDER,
                CrmSyncedContact.phone == phone,
            ).limit(1)
        ).scalar_one_or_none()
        if pool:
            person_id = pool.external_contact_id
    if not person_id:
        result = _loads(recipient.result_json)
        person_id = str(result.get("pipedrive_person_id") or "").strip() or None
    if not person_id:
        if force:
            raise PipedriveContactSyncError("No matching Pipedrive person found for this respondent")
        return {"ok": True, "skipped": True, "reason": "person_not_found"}

    note_body = survey_result_summary(order, recipient)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    with httpx.Client(timeout=30.0) as client:
        res = client.post(
            f"{PIPEDRIVE_API_BASE}/notes",
            headers=headers,
            json={"content": note_body, "person_id": int(person_id)},
        )
    if res.status_code >= 400:
        raise PipedriveContactSyncError(f"Pipedrive note create failed: {res.text[:300]}")

    merged = _loads(recipient.result_json)
    merged.update(
        {
            "pipedrive_person_id": person_id,
            "pipedrive_synced_at": datetime.utcnow().isoformat(),
            "pipedrive_sync_note": note_body.split("\n", 1)[0],
        }
    )
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    db.add(recipient)

    domain = str(cfg.get("company_domain") or "").strip()
    contact_url = f"https://{domain}.pipedrive.com/person/{person_id}" if domain else ""
    return {
        "ok": True,
        "provider": PROVIDER,
        "person_id": person_id,
        "contact_url": contact_url,
        "note_created": True,
    }
