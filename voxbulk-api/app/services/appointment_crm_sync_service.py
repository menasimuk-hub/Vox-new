"""Sync upcoming appointments from connected CRM providers."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.organisation import Organisation
from app.services.appointment_log_service import append_log
from app.services.appointment_settings_service import get_config
from app.services.crm_providers import CRM_CONFIG_COLUMNS
from app.services.org_enabled_services import is_service_enabled, org_service_maps

logger = logging.getLogger(__name__)

HUBSPOT_CONTACTS_URL = "https://api.hubapi.com/crm/v3/objects/contacts"


@dataclass(frozen=True)
class AppointmentData:
    crm_source: str
    crm_record_id: str
    contact_name: str
    contact_phone: str
    contact_email: str | None
    appointment_datetime: datetime
    timezone: str = "Europe/London"
    location: str | None = None
    branch: str | None = None
    service_type: str | None = None


def _org_has_crm_connected(db: Session, org_id: str, provider: str) -> bool:
    col = CRM_CONFIG_COLUMNS.get(provider)
    if not col:
        return False
    org = db.get(Organisation, org_id)
    if org is None:
        return False
    raw = getattr(org, col, None)
    if not raw or not str(raw).strip():
        return False
    if provider == "hubspot":
        from app.services.hubspot_connection_service import hubspot_status

        return bool(hubspot_status(db, org_id).get("connected"))
    if provider == "pipedrive":
        from app.services.pipedrive_connection_service import pipedrive_status

        return bool(pipedrive_status(db, org_id).get("connected"))
    if provider == "zoho_crm":
        from app.services.zoho_crm_connection_service import zoho_crm_status

        return bool(zoho_crm_status(db, org_id).get("connected"))
    return False


def _contact_item_to_appointment(item: dict[str, Any], *, date_prop: str) -> AppointmentData | None:
    if not isinstance(item, dict):
        return None
    hs_id = str(item.get("id") or "").strip()
    props_raw = item.get("properties") if isinstance(item.get("properties"), dict) else {}
    date_raw = str(props_raw.get(date_prop) or "").strip()
    if not hs_id or not date_raw:
        return None
    try:
        appt_dt = datetime.fromisoformat(date_raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None
    first = str(props_raw.get("firstname") or "").strip()
    last = str(props_raw.get("lastname") or "").strip()
    name = " ".join(x for x in (first, last) if x).strip() or str(props_raw.get("email") or "Contact")
    phone = str(props_raw.get("phone") or "").strip()
    if not phone:
        return None
    return AppointmentData(
        crm_source="hubspot",
        crm_record_id=hs_id,
        contact_name=name,
        contact_phone=phone,
        contact_email=str(props_raw.get("email") or "").strip() or None,
        appointment_datetime=appt_dt,
    )


def _fetch_hubspot_appointments(db: Session, org_id: str) -> list[AppointmentData]:
    from app.services.hubspot_connection_service import _ensure_access_token, get_hubspot_config, hubspot_status
    from app.services.hubspot_list_service import HubspotListError, fetch_list_contacts

    if not hubspot_status(db, org_id).get("connected"):
        return []
    cfg = get_hubspot_config(db, org_id)
    token = _ensure_access_token(db, org_id)
    if not token:
        return []

    appt_cfg = get_config(db, org_id)
    date_prop = str(appt_cfg.get("crm_date_property") or "appointment_date").strip() or "appointment_date"
    props = ["firstname", "lastname", "email", "phone", date_prop]
    list_id = str(cfg.get("appointment_list_id") or "").strip()

    out: list[AppointmentData] = []
    try:
        if list_id:
            items = fetch_list_contacts(token, list_id, props)
            for item in items:
                row = _contact_item_to_appointment(item, date_prop=date_prop)
                if row:
                    out.append(row)
            return out

        after: str | None = None
        with httpx.Client(timeout=60.0) as client:
            while True:
                params: dict[str, Any] = {"limit": 100, "properties": ",".join(props)}
                if after:
                    params["after"] = after
                res = client.get(
                    HUBSPOT_CONTACTS_URL,
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                )
                if res.status_code >= 400:
                    logger.warning("hubspot_appointment_sync_failed org=%s status=%s", org_id, res.status_code)
                    break
                body = res.json() or {}
                for item in body.get("results") or []:
                    row = _contact_item_to_appointment(item, date_prop=date_prop)
                    if row:
                        out.append(row)
                paging = body.get("paging") or {}
                next_link = paging.get("next") if isinstance(paging, dict) else None
                after = None
                if isinstance(next_link, dict):
                    after = str(next_link.get("after") or "").strip() or None
                if not after:
                    break
    except HubspotListError as exc:
        logger.warning("hubspot_appointment_list_sync_failed org=%s err=%s", org_id, str(exc)[:200])
    except Exception:
        logger.exception("hubspot_appointment_sync_error org=%s", org_id)
    return out


def _fetch_pipedrive_appointments(db: Session, org_id: str) -> list[AppointmentData]:
    _ = (db, org_id)
    return []


def _fetch_zoho_appointments(db: Session, org_id: str) -> list[AppointmentData]:
    _ = (db, org_id)
    return []


def _upsert_appointment(db: Session, org_id: str, data: AppointmentData) -> tuple[Appointment, bool]:
    existing = db.execute(
        select(Appointment).where(
            Appointment.org_id == org_id,
            Appointment.crm_source == data.crm_source,
            Appointment.crm_record_id == data.crm_record_id,
        )
    ).scalar_one_or_none()
    now = datetime.utcnow()
    if existing is None:
        row = Appointment(
            id=str(uuid.uuid4()),
            org_id=org_id,
            contact_name=data.contact_name,
            contact_phone=data.contact_phone,
            contact_email=data.contact_email,
            appointment_datetime=data.appointment_datetime,
            timezone=data.timezone,
            location=data.location,
            branch=data.branch,
            service_type=data.service_type,
            status="scheduled",
            crm_source=data.crm_source,
            crm_record_id=data.crm_record_id,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        append_log(db, appointment_id=row.id, event_type="crm_sync_created", detail={"crm_source": data.crm_source})
        return row, True

    changed = (
        existing.contact_name != data.contact_name
        or existing.contact_phone != data.contact_phone
        or existing.appointment_datetime != data.appointment_datetime
    )
    existing.contact_name = data.contact_name
    existing.contact_phone = data.contact_phone
    existing.contact_email = data.contact_email
    existing.appointment_datetime = data.appointment_datetime
    existing.timezone = data.timezone
    existing.location = data.location
    existing.branch = data.branch
    existing.service_type = data.service_type
    existing.updated_at = now
    db.add(existing)
    if changed:
        append_log(db, appointment_id=existing.id, event_type="crm_sync_updated", detail={"crm_source": data.crm_source})
    return existing, False


def sync_org_appointments(db: Session, org_id: str) -> dict[str, Any]:
    rows: list[AppointmentData] = []
    if _org_has_crm_connected(db, org_id, "hubspot"):
        rows.extend(_fetch_hubspot_appointments(db, org_id))
    if _org_has_crm_connected(db, org_id, "pipedrive"):
        rows.extend(_fetch_pipedrive_appointments(db, org_id))
    if _org_has_crm_connected(db, org_id, "zoho_crm"):
        rows.extend(_fetch_zoho_appointments(db, org_id))

    created = 0
    updated = 0
    for data in rows:
        _row, is_new = _upsert_appointment(db, org_id, data)
        if is_new:
            created += 1
        else:
            updated += 1
    db.commit()
    return {"org_id": org_id, "fetched": len(rows), "created": created, "updated": updated, "synced": created + updated}


def sync_all_orgs(db: Session) -> dict[str, Any]:
    orgs = list(db.execute(select(Organisation).where(Organisation.deletion_status == "active")).scalars())
    results: list[dict[str, Any]] = []
    for org in orgs:
        _allowed, _enabled, visible = org_service_maps(org, db)
        if not is_service_enabled(visible, "appointments"):
            continue
        if not any(_org_has_crm_connected(db, org.id, p) for p in ("hubspot", "pipedrive", "zoho_crm")):
            continue
        try:
            results.append(sync_org_appointments(db, org.id))
        except Exception:
            logger.exception("appointment_crm_sync_failed org=%s", org.id)
    return {"orgs_synced": len(results), "results": results}
