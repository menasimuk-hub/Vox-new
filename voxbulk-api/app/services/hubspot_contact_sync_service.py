"""HubSpot contact sync v1 — pull contacts into VoxBulk, import to surveys, write-back results."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.hubspot_contact import HubspotContact
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.hubspot_connection_service import (
    HUBSPOT_CONTACTS_URL,
    _ensure_access_token,
    _search_contact_by_email,
    get_hubspot_config,
    hubspot_status,
    platform_oauth_configured,
    save_hubspot_config,
)
from app.services.messaging_log_service import normalize_e164

logger = logging.getLogger(__name__)

HUBSPOT_NOTES_URL = "https://api.hubapi.com/crm/v3/objects/notes"
DEFAULT_SYNC_LIMIT = 100
NOTE_TO_CONTACT_ASSOCIATION_TYPE_ID = 202


class HubspotContactSyncError(Exception):
    pass


def default_field_map() -> dict[str, str]:
    return {
        "first_name": "firstname",
        "last_name": "lastname",
        "email": "email",
        "phone": "phone",
    }


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _hubspot_platform_config(db: Session) -> tuple[dict[str, Any], bool]:
    try:
        from app.services.provider_settings import ProviderSettingsService

        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="hubspot")
        if isinstance(cfg, dict):
            return cfg, bool(enabled)
    except Exception:
        pass
    return {}, False


def is_sync_v1_enabled(db: Session) -> bool:
    env_raw = os.environ.get("HUBSPOT_CONTACT_SYNC_V1_ENABLED", "").strip().lower()
    if env_raw in {"0", "false", "no", "off"}:
        return False
    if env_raw in {"1", "true", "yes", "on"}:
        return platform_oauth_configured(db)

    cfg, platform_enabled = _hubspot_platform_config(db)
    if not platform_enabled:
        return False
    return cfg.get("contact_sync_v1_enabled") is True


def require_sync_v1_enabled(db: Session) -> None:
    if not is_sync_v1_enabled(db):
        raise HubspotContactSyncError("HubSpot contact sync is not enabled")


def read_field_map(cfg: dict[str, Any]) -> dict[str, str]:
    raw = cfg.get("field_map")
    if not isinstance(raw, dict):
        return default_field_map()
    merged = default_field_map()
    for key in merged:
        val = str(raw.get(key) or merged[key]).strip()
        if val:
            merged[key] = val
    return merged


def sync_status_extras(db: Session, org_id: str, cfg: dict[str, Any]) -> dict[str, Any]:
    count = int(
        db.execute(select(func.count()).select_from(HubspotContact).where(HubspotContact.org_id == org_id)).scalar_one()
        or 0
    )
    return {
        "sync_settings_enabled": is_sync_v1_enabled(db),
        "field_map": read_field_map(cfg),
        "auto_sync_results_back": cfg.get("auto_sync_results_back") is not False,
        "last_sync_at": cfg.get("last_sync_at"),
        "contact_count": count,
        "last_sync_summary": cfg.get("last_sync_summary"),
    }


def update_hubspot_sync_settings(
    db: Session,
    org_id: str,
    *,
    field_map: dict[str, str] | None = None,
    auto_sync_results_back: bool | None = None,
) -> dict[str, Any]:
    require_sync_v1_enabled(db)
    from app.models.organisation import Organisation

    org = db.get(Organisation, org_id)
    if org is None:
        raise ValueError("Organisation not found")
    cfg = _loads(org.hubspot_config_json)
    if field_map is not None:
        cleaned: dict[str, str] = {}
        defaults = default_field_map()
        for key in defaults:
            val = str(field_map.get(key) or defaults[key]).strip()
            if val:
                cleaned[key] = val[:128]
        cfg["field_map"] = cleaned
    if auto_sync_results_back is not None:
        cfg["auto_sync_results_back"] = bool(auto_sync_results_back)
    org.hubspot_config_json = json.dumps(cfg, ensure_ascii=False)
    db.add(org)
    db.commit()
    return hubspot_status(db, org_id)


def _map_contact_properties(props: dict[str, Any], field_map: dict[str, str]) -> dict[str, str | None]:
    first = str(props.get(field_map["first_name"]) or "").strip()
    last = str(props.get(field_map["last_name"]) or "").strip()
    name = " ".join(p for p in (first, last) if p).strip()
    email = str(props.get(field_map["email"]) or "").strip() or None
    phone_raw = str(props.get(field_map["phone"]) or "").strip()
    phone: str | None = None
    if phone_raw:
        try:
            phone = normalize_e164(phone_raw)
        except ValueError:
            phone = None
    return {"name": name or email or "Contact", "email": email, "phone": phone}


def fetch_and_upsert_contacts(db: Session, org_id: str, *, limit: int = DEFAULT_SYNC_LIMIT) -> dict[str, Any]:
    require_sync_v1_enabled(db)
    status = hubspot_status(db, org_id)
    if not status.get("connected"):
        raise HubspotContactSyncError("Connect HubSpot before syncing contacts")

    cfg = get_hubspot_config(db, org_id)
    field_map = read_field_map(cfg)
    token = _ensure_access_token(db, org_id)
    props = list({field_map["first_name"], field_map["last_name"], field_map["email"], field_map["phone"]})
    params: dict[str, Any] = {"limit": min(max(1, limit), DEFAULT_SYNC_LIMIT), "properties": ",".join(props)}

    with httpx.Client(timeout=45.0) as client:
        res = client.get(
            HUBSPOT_CONTACTS_URL,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
    if res.status_code >= 400:
        raise HubspotContactSyncError(f"HubSpot contact fetch failed: {res.text[:300]}")

    body = res.json() or {}
    results = body.get("results") or []
    paging = body.get("paging") or {}
    has_more = bool(paging.get("next"))

    imported = 0
    updated = 0
    skipped = 0
    now = datetime.utcnow()

    for item in results:
        if not isinstance(item, dict):
            skipped += 1
            continue
        hs_id = str(item.get("id") or "").strip()
        if not hs_id:
            skipped += 1
            continue
        props_raw = item.get("properties") if isinstance(item.get("properties"), dict) else {}
        mapped = _map_contact_properties(props_raw, field_map)
        if not mapped.get("email") and not mapped.get("phone"):
            skipped += 1
            continue

        existing = db.execute(
            select(HubspotContact).where(
                HubspotContact.org_id == org_id,
                HubspotContact.hubspot_contact_id == hs_id,
            )
        ).scalar_one_or_none()

        if existing is None:
            db.add(
                HubspotContact(
                    id=str(uuid.uuid4()),
                    org_id=org_id,
                    hubspot_contact_id=hs_id,
                    name=str(mapped["name"] or "Contact"),
                    email=mapped.get("email"),
                    phone=mapped.get("phone"),
                    raw_properties_json=json.dumps(props_raw, ensure_ascii=False),
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
            existing.raw_properties_json = json.dumps(props_raw, ensure_ascii=False)
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
    save_hubspot_config(db, org_id, cfg_update)
    db.commit()

    return {"ok": True, **summary, "message": f"Synced {imported + updated} contact(s) from HubSpot"}


def list_contacts(db: Session, org_id: str, *, limit: int = 50) -> dict[str, Any]:
    require_sync_v1_enabled(db)
    lim = min(max(1, limit), 100)
    rows = list(
        db.execute(
            select(HubspotContact)
            .where(HubspotContact.org_id == org_id)
            .order_by(HubspotContact.synced_at.desc())
            .limit(lim)
        ).scalars().all()
    )
    return {
        "ok": True,
        "items": [
            {
                "id": r.id,
                "hubspot_contact_id": r.hubspot_contact_id,
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
    require_sync_v1_enabled(db)
    from app.services.platform_catalog_service import ServiceOrderService

    order = ServiceOrderService.get_order(db, order_id, org_id=org_id)
    if order is None:
        raise HubspotContactSyncError("Order not found")
    if order.service_code != "survey":
        raise HubspotContactSyncError("HubSpot import is only supported for survey campaigns in v1")
    if order.status == "completed":
        raise HubspotContactSyncError("Cannot import contacts into a completed campaign")
    if str(order.payment_status or "").lower() == "approved":
        raise HubspotContactSyncError("Cannot import contacts after payment is approved")

    id_set = {str(x).strip() for x in contact_ids if str(x).strip()}
    if not id_set:
        raise HubspotContactSyncError("Select at least one contact")

    contacts = list(
        db.execute(
            select(HubspotContact).where(
                HubspotContact.org_id == org_id,
                HubspotContact.id.in_(id_set),
            )
        ).scalars().all()
    )
    if not contacts:
        raise HubspotContactSyncError("No matching synced contacts found")

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


def _survey_result_summary(order: ServiceOrder, recipient: ServiceOrderRecipient) -> str:
    try:
        result = json.loads(recipient.result_json or "{}")
    except Exception:
        result = {}
    if not isinstance(result, dict):
        result = {}
    analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
    parts = [f"VoxBulk WA survey completed: {order.title}"]
    sentiment = str(analysis.get("sentiment") or result.get("sentiment") or "").strip()
    if sentiment:
        parts.append(f"Sentiment: {sentiment}")
    score = analysis.get("recommend_score", result.get("recommend_score"))
    if score is not None:
        parts.append(f"Score: {score}")
    summary = str(analysis.get("short_summary") or result.get("short_summary") or "").strip()
    if summary:
        parts.append(summary[:500])
    parts.append(f"Completed at: {datetime.utcnow().isoformat()}Z")
    return " · ".join(parts)


def _create_hubspot_note(token: str, *, contact_id: str, body: str) -> None:
    payload = {
        "properties": {
            "hs_timestamp": datetime.utcnow().isoformat(),
            "hs_note_body": body[:65535],
        },
        "associations": [
            {
                "to": {"id": contact_id},
                "types": [
                    {
                        "associationCategory": "HUBSPOT_DEFINED",
                        "associationTypeId": NOTE_TO_CONTACT_ASSOCIATION_TYPE_ID,
                    }
                ],
            }
        ],
    }
    with httpx.Client(timeout=30.0) as client:
        res = client.post(
            HUBSPOT_NOTES_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
        )
    if res.status_code >= 400:
        raise HubspotContactSyncError(f"HubSpot note create failed: {res.text[:300]}")


def sync_survey_result_to_hubspot(
    db: Session,
    org_id: str,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
) -> dict[str, Any]:
    require_sync_v1_enabled(db)
    status = hubspot_status(db, org_id)
    if not status.get("connected") or not status.get("auto_sync_results_back"):
        return {"ok": True, "skipped": True}

    cfg = get_hubspot_config(db, org_id)
    if cfg.get("auto_sync_results_back") is False:
        return {"ok": True, "skipped": True}

    email = str(recipient.email or "").strip()
    phone = str(recipient.phone or "").strip()
    if not email and not phone:
        return {"ok": True, "skipped": True, "reason": "no_email_or_phone"}

    token = _ensure_access_token(db, org_id)
    contact_id = _search_contact_by_email(token, email) if email else None
    if not contact_id and phone:
        pool = db.execute(
            select(HubspotContact)
            .where(HubspotContact.org_id == org_id, HubspotContact.phone == phone)
            .limit(1)
        ).scalar_one_or_none()
        if pool:
            contact_id = pool.hubspot_contact_id

    if not contact_id:
        return {"ok": True, "skipped": True, "reason": "contact_not_found_in_hubspot"}

    note_body = _survey_result_summary(order, recipient)
    _create_hubspot_note(token, contact_id=contact_id, body=note_body)
    return {"ok": True, "contact_id": contact_id}


def maybe_sync_survey_result_to_hubspot(db: Session, order: ServiceOrder, recipient: ServiceOrderRecipient) -> None:
    if order.service_code != "survey":
        return
    if not is_sync_v1_enabled(db):
        return
    try:
        sync_survey_result_to_hubspot(db, order.org_id, order=order, recipient=recipient)
    except Exception as exc:
        logger.warning(
            "hubspot_survey_writeback_failed org=%s order=%s recipient=%s err=%s",
            order.org_id,
            order.id,
            recipient.id,
            str(exc)[:200],
        )
