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
HUBSPOT_OBJECTS_BASE = "https://api.hubapi.com/crm/v3/objects"
HUBSPOT_OBJECT_PHONE_KEYS = (
    "phone",
    "mobilephone",
    "hs_phone_number",
    "phone_number",
    "contact_phone",
)
HUBSPOT_OBJECT_NAME_KEYS = ("firstname", "lastname", "name", "dealname", "company", "email")
HUBSPOT_OBJECT_BRANCH_KEYS = ("branch", "city")
HUBSPOT_OBJECT_SERVICE_KEYS = ("service_type", "jobtitle")
DEFAULT_CRM_DATE_PROP = "appointment_date"
DEFAULT_CRM_PHONE_PROP = "phone"
DEFAULT_CRM_NAME_PROP = "name"
DEFAULT_CRM_STATUS_PROP = "voxbulk_appointment_status"
DEFAULT_CRM_BUCKET_PROP = "voxbulk_appointment_bucket"


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


def _parse_hubspot_datetime(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    # HubSpot datetime can arrive as ISO string or epoch milliseconds.
    if raw.isdigit():
        try:
            return datetime.utcfromtimestamp(int(raw) / 1000.0)
        except Exception:
            return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _parse_datetime_value(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        try:
            return datetime.utcfromtimestamp(int(raw) / 1000.0)
        except Exception:
            return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _first_non_empty(props: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        val = str(props.get(key) or "").strip()
        if val:
            return val
    return ""


def _hubspot_item_to_appointment(
    item: dict[str, Any],
    *,
    date_prop: str,
    object_type: str,
    phone_prop: str | None = None,
    name_prop: str | None = None,
) -> AppointmentData | None:
    if not isinstance(item, dict):
        return None
    hs_id = str(item.get("id") or "").strip()
    props = item.get("properties") if isinstance(item.get("properties"), dict) else {}
    if not hs_id or not isinstance(props, dict):
        return None
    appt_dt = _parse_datetime_value(props.get(date_prop))
    if appt_dt is None:
        return None

    phone = ""
    if phone_prop:
        phone = str(props.get(phone_prop) or "").strip()
    if not phone:
        phone = _first_non_empty(props, HUBSPOT_OBJECT_PHONE_KEYS)
    if not phone:
        return None

    contact_name = ""
    if name_prop:
        contact_name = str(props.get(name_prop) or "").strip()
    if not contact_name:
        first = str(props.get("firstname") or "").strip()
        last = str(props.get("lastname") or "").strip()
        contact_name = " ".join(x for x in (first, last) if x).strip()
    if not contact_name:
        contact_name = _first_non_empty(props, HUBSPOT_OBJECT_NAME_KEYS)
    if not contact_name:
        contact_name = f"{object_type.title()} {hs_id[:8]}"
    email = str(props.get("email") or "").strip() or None
    crm_record_id = hs_id if object_type == "contacts" else f"{object_type}:{hs_id}"
    return AppointmentData(
        crm_source="hubspot",
        crm_record_id=crm_record_id,
        contact_name=contact_name,
        contact_phone=phone,
        contact_email=email,
        appointment_datetime=appt_dt,
        branch=_first_non_empty(props, HUBSPOT_OBJECT_BRANCH_KEYS) or None,
        service_type=_first_non_empty(props, HUBSPOT_OBJECT_SERVICE_KEYS) or None,
    )


def _crm_mapping(appt_cfg: dict[str, Any]) -> dict[str, str]:
    return {
        "date_prop": str(appt_cfg.get("crm_date_property") or DEFAULT_CRM_DATE_PROP).strip() or DEFAULT_CRM_DATE_PROP,
        "phone_prop": str(appt_cfg.get("crm_phone_property") or DEFAULT_CRM_PHONE_PROP).strip() or DEFAULT_CRM_PHONE_PROP,
        "name_prop": str(appt_cfg.get("crm_name_property") or DEFAULT_CRM_NAME_PROP).strip() or DEFAULT_CRM_NAME_PROP,
        "status_prop": str(appt_cfg.get("crm_status_property") or DEFAULT_CRM_STATUS_PROP).strip() or DEFAULT_CRM_STATUS_PROP,
        "bucket_prop": str(appt_cfg.get("crm_bucket_property") or DEFAULT_CRM_BUCKET_PROP).strip() or DEFAULT_CRM_BUCKET_PROP,
    }


def _search_hubspot_object_rows(
    token: str,
    *,
    object_type: str,
    date_prop: str,
    properties: list[str],
    max_results: int = 5000,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    after: str | None = None
    cap = min(max(1, max_results), 5000)
    with httpx.Client(timeout=60.0) as client:
        while len(out) < cap:
            payload: dict[str, Any] = {
                "filterGroups": [
                    {"filters": [{"propertyName": date_prop, "operator": "HAS_PROPERTY"}]},
                ],
                "properties": properties,
                "limit": min(100, cap - len(out)),
            }
            if after:
                payload["after"] = after
            res = client.post(
                f"{HUBSPOT_OBJECTS_BASE}/{object_type}/search",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
            )
            if res.status_code >= 400:
                raise ValueError(f"HubSpot object search failed: {res.text[:300]}")
            body = res.json() or {}
            rows = body.get("results") or []
            for row in rows:
                if isinstance(row, dict):
                    out.append(row)
                    if len(out) >= cap:
                        break
            paging = body.get("paging") if isinstance(body, dict) else None
            nxt = paging.get("next") if isinstance(paging, dict) else None
            after = str(nxt.get("after") or "").strip() if isinstance(nxt, dict) else ""
            if not after:
                break
    return out


def _fetch_hubspot_appointments(db: Session, org_id: str) -> list[AppointmentData]:
    from app.services.hubspot_connection_service import (
        _ensure_access_token,
        get_hubspot_config,
        hubspot_status,
        update_hubspot_settings,
    )
    from app.services.hubspot_list_service import (
        HubspotListError,
        ensure_appointment_source_list,
        search_contacts_with_appointment_date,
        sync_contacts_to_list,
    )

    if not hubspot_status(db, org_id).get("connected"):
        return []
    cfg = get_hubspot_config(db, org_id)
    token = _ensure_access_token(db, org_id)
    if not token:
        return []

    appt_cfg = get_config(db, org_id)
    mapping = _crm_mapping(appt_cfg)
    date_prop = mapping["date_prop"]
    phone_prop = mapping["phone_prop"]
    name_prop = mapping["name_prop"]
    object_type = str(appt_cfg.get("crm_object") or "contacts").strip().lower() or "contacts"
    props = [
        *HUBSPOT_OBJECT_NAME_KEYS,
        *HUBSPOT_OBJECT_PHONE_KEYS,
        *HUBSPOT_OBJECT_BRANCH_KEYS,
        *HUBSPOT_OBJECT_SERVICE_KEYS,
        name_prop,
        phone_prop,
        date_prop,
    ]
    configured_list_id = str(cfg.get("appointment_list_id") or "").strip()

    out: list[AppointmentData] = []
    if object_type != "contacts":
        try:
            items = _search_hubspot_object_rows(
                token,
                object_type=object_type,
                date_prop=date_prop,
                properties=props,
            )
            for item in items:
                row = _hubspot_item_to_appointment(
                    item,
                    date_prop=date_prop,
                    object_type=object_type,
                    phone_prop=phone_prop,
                    name_prop=name_prop,
                )
                if row:
                    out.append(row)
        except Exception:
            logger.exception("hubspot_appointment_object_sync_error org=%s object=%s", org_id, object_type)
        return out

    try:
        items = search_contacts_with_appointment_date(token, date_prop, props)
        source_list_id = ensure_appointment_source_list(token, configured_list_id or None)
        if source_list_id != configured_list_id:
            update_hubspot_settings(db, org_id, appointment_list_id=source_list_id)
        if source_list_id and items:
            contact_ids = [str(item.get("id") or "").strip() for item in items if str(item.get("id") or "").strip()]
            try:
                added = sync_contacts_to_list(token, source_list_id, contact_ids)
                logger.info(
                    "hubspot_appointment_list_auto_sync org=%s list=%s contacts=%s",
                    org_id,
                    source_list_id,
                    added,
                )
            except HubspotListError as exc:
                logger.warning(
                    "hubspot_appointment_list_auto_sync_failed org=%s list=%s err=%s",
                    org_id,
                    source_list_id,
                    str(exc)[:200],
                )
        for item in items:
            row = _hubspot_item_to_appointment(
                item,
                date_prop=date_prop,
                object_type="contacts",
                phone_prop=phone_prop,
                name_prop=name_prop,
            )
            if row:
                out.append(row)
    except HubspotListError as exc:
        logger.warning("hubspot_appointment_list_sync_failed org=%s err=%s", org_id, str(exc)[:200])
    except Exception:
        logger.exception("hubspot_appointment_sync_error org=%s", org_id)
    return out


def _fetch_pipedrive_appointments(db: Session, org_id: str) -> list[AppointmentData]:
    from app.services.pipedrive_connection_service import (
        PIPEDRIVE_API_BASE,
        _ensure_access_token,
        pipedrive_status,
    )

    if not pipedrive_status(db, org_id).get("connected"):
        return []

    appt_cfg = get_config(db, org_id)
    mapping = _crm_mapping(appt_cfg)
    date_prop = mapping["date_prop"]
    phone_prop = mapping["phone_prop"]
    name_prop = mapping["name_prop"]
    token = _ensure_access_token(db, org_id)
    out: list[AppointmentData] = []

    with httpx.Client(timeout=45.0) as client:
        res = client.get(
            f"{PIPEDRIVE_API_BASE}/deals",
            headers={"Authorization": f"Bearer {token}"},
            params={"status": "open", "limit": 500, "start": 0},
        )
    if res.status_code >= 400:
        logger.warning("pipedrive_appointment_sync_failed org=%s status=%s", org_id, res.status_code)
        return out

    rows = (res.json() or {}).get("data") or []
    for item in rows:
        if not isinstance(item, dict):
            continue
        deal_id = str(item.get("id") or "").strip()
        if not deal_id:
            continue
        appt_dt = _parse_datetime_value(item.get(date_prop))
        if appt_dt is None:
            continue

        phone = str(item.get(phone_prop) or "").strip()
        person = item.get("person_id")
        if isinstance(person, dict):
            person_name = str(person.get("name") or "").strip()
            person_email = str(person.get("email") or "").strip() or None
            person_phone = str(person.get("phone") or "").strip()
        else:
            person_name = ""
            person_email = None
            person_phone = ""
        if not phone:
            phone = person_phone
        if not phone:
            continue

        contact_name = str(item.get(name_prop) or "").strip() or person_name or str(item.get("title") or "").strip()
        if not contact_name:
            contact_name = f"Pipedrive Deal {deal_id}"
        branch = str(item.get("stage_name") or "").strip() or None
        service_type = str(item.get("title") or "").strip() or None
        out.append(
            AppointmentData(
                crm_source="pipedrive",
                crm_record_id=deal_id,
                contact_name=contact_name,
                contact_phone=phone,
                contact_email=person_email,
                appointment_datetime=appt_dt,
                branch=branch,
                service_type=service_type,
            )
        )
    return out


def _fetch_zoho_appointments(db: Session, org_id: str) -> list[AppointmentData]:
    from app.services.zoho_crm_connection_service import _ensure_access_token, zoho_crm_status

    if not zoho_crm_status(db, org_id).get("connected"):
        return []

    appt_cfg = get_config(db, org_id)
    mapping = _crm_mapping(appt_cfg)
    date_prop = mapping["date_prop"]
    phone_prop = mapping["phone_prop"]
    name_prop = mapping["name_prop"]
    token, api_domain = _ensure_access_token(db, org_id)
    base = f"https://{str(api_domain).strip().lstrip('https://').lstrip('http://')}"
    out: list[AppointmentData] = []
    fields = ",".join(
        sorted(
            {
                "Deal_Name",
                "Stage",
                "Contact_Name",
                "Email",
                date_prop,
                phone_prop,
                name_prop,
            }
        )
    )
    with httpx.Client(timeout=45.0) as client:
        res = client.get(
            f"{base}/crm/v2/Deals",
            headers={"Authorization": f"Zoho-oauthtoken {token}"},
            params={"fields": fields, "per_page": 200, "page": 1},
        )
    if res.status_code >= 400:
        logger.warning("zoho_appointment_sync_failed org=%s status=%s", org_id, res.status_code)
        return out

    rows = (res.json() or {}).get("data") or []
    for item in rows:
        if not isinstance(item, dict):
            continue
        deal_id = str(item.get("id") or "").strip()
        if not deal_id:
            continue
        appt_dt = _parse_datetime_value(item.get(date_prop))
        if appt_dt is None:
            continue
        phone = str(item.get(phone_prop) or "").strip()
        if not phone:
            continue
        deal_name = str(item.get("Deal_Name") or "").strip()
        contact_name = str(item.get(name_prop) or "").strip()
        if not contact_name:
            contact = item.get("Contact_Name")
            if isinstance(contact, dict):
                contact_name = str(contact.get("name") or "").strip()
        contact_name = contact_name or deal_name or f"Zoho Deal {deal_id}"
        email = str(item.get("Email") or "").strip() or None
        branch = str(item.get("Stage") or "").strip() or None
        out.append(
            AppointmentData(
                crm_source="zoho_crm",
                crm_record_id=deal_id,
                contact_name=contact_name,
                contact_phone=phone,
                contact_email=email,
                appointment_datetime=appt_dt,
                branch=branch,
                service_type=deal_name or None,
            )
        )
    return out


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
        from app.services.appointment_calendar_service import maybe_sync_appointment_calendar

        maybe_sync_appointment_calendar(db, row)
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
    from app.services.appointment_calendar_service import maybe_sync_appointment_calendar

    row = existing
    maybe_sync_appointment_calendar(db, row)
    return row, False


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

    result = {
        "org_id": org_id,
        "fetched": len(rows),
        "created": created,
        "updated": updated,
        "synced": created + updated,
    }
    try:
        from app.services.appointment_settings_service import save_config

        save_config(
            db,
            org_id,
            {
                "last_crm_sync_at": datetime.utcnow().isoformat(),
                "last_crm_sync_fetched": len(rows),
                "last_crm_sync_created": created,
                "last_crm_sync_updated": updated,
            },
        )
    except Exception:
        logger.exception("appointment_crm_sync_save_summary_failed org=%s", org_id)
    return result


def get_crm_sync_status(db: Session, org_id: str) -> dict[str, Any]:
    """Dashboard-facing CRM sync readiness (no scripts required)."""
    from app.services.appointment_settings_service import get_config
    from app.services.hubspot_connection_service import get_hubspot_config, hubspot_status
    from app.services.hubspot_list_service import (
        DEFAULT_APPOINTMENT_LIST_NAME,
        HubspotListError,
        find_hubspot_list_id_by_name,
        search_contacts_with_appointment_date,
    )

    appt_cfg = get_config(db, org_id)
    mapping = _crm_mapping(appt_cfg)
    crm_object = str(appt_cfg.get("crm_object") or "contacts").strip().lower() or "contacts"
    date_prop = mapping["date_prop"]
    phone_prop = mapping["phone_prop"]
    name_prop = mapping["name_prop"]
    provider: str | None = None
    if _org_has_crm_connected(db, org_id, "hubspot"):
        provider = "hubspot"
    elif _org_has_crm_connected(db, org_id, "pipedrive"):
        provider = "pipedrive"
    elif _org_has_crm_connected(db, org_id, "zoho_crm"):
        provider = "zoho_crm"

    out: dict[str, Any] = {
        "crm_connected": provider is not None,
        "crm_provider": provider,
        "crm_object": crm_object,
        "date_property": date_prop,
        "eligible_contacts": 0,
        "appointment_list_id": None,
        "appointment_list_name": None,
        "last_sync_at": appt_cfg.get("last_crm_sync_at"),
        "last_sync_fetched": int(appt_cfg.get("last_crm_sync_fetched") or 0),
        "last_sync_created": int(appt_cfg.get("last_crm_sync_created") or 0),
        "last_sync_updated": int(appt_cfg.get("last_crm_sync_updated") or 0),
        "ready": False,
        "message": "Connect a CRM in Settings → Integrations to sync appointments.",
    }

    if not provider:
        return out

    if provider == "hubspot":
        hs = hubspot_status(db, org_id)
        if not hs.get("connected"):
            out["message"] = "HubSpot is not connected — open Settings → Integrations → HubSpot and paste your service key."
            return out
        if crm_object != "contacts":
            try:
                from app.services.hubspot_connection_service import _ensure_access_token

                token = _ensure_access_token(db, org_id)
                items = _search_hubspot_object_rows(
                    token,
                    object_type=crm_object,
                    date_prop=date_prop,
                    properties=[*HUBSPOT_OBJECT_NAME_KEYS, *HUBSPOT_OBJECT_PHONE_KEYS, name_prop, phone_prop, date_prop],
                    max_results=5000,
                )
                eligible = 0
                for item in items:
                    if _hubspot_item_to_appointment(
                        item,
                        date_prop=date_prop,
                        object_type=crm_object,
                        phone_prop=phone_prop,
                        name_prop=name_prop,
                    ):
                        eligible += 1
                out["eligible_contacts"] = eligible
                if eligible > 0:
                    out["ready"] = True
                    out["message"] = (
                        f"{eligible} HubSpot {crm_object} record(s) have phone + {date_prop}. "
                        "Click Sync CRM to import them."
                    )
                else:
                    out["message"] = (
                        f"No HubSpot {crm_object} records have both phone and {date_prop} set. "
                        "Update those properties, then click Sync CRM."
                    )
            except Exception as exc:
                out["message"] = str(exc)[:240] or f"HubSpot {crm_object} check failed"
            return out
        cfg = get_hubspot_config(db, org_id)
        list_id = str(cfg.get("appointment_list_id") or "").strip() or None
        list_name = DEFAULT_APPOINTMENT_LIST_NAME
        if list_id:
            from app.services.hubspot_list_service import list_hubspot_lists
            from app.services.hubspot_connection_service import _ensure_access_token

            token = _ensure_access_token(db, org_id)
            try:
                for row in list_hubspot_lists(token, limit=100):
                    if str(row.get("id") or "") == list_id:
                        list_name = str(row.get("name") or list_name)
                        break
            except HubspotListError:
                pass
        else:
            token = None
            try:
                from app.services.hubspot_connection_service import _ensure_access_token

                token = _ensure_access_token(db, org_id)
                list_id = find_hubspot_list_id_by_name(token, DEFAULT_APPOINTMENT_LIST_NAME)
            except Exception:
                list_id = None

        out["appointment_list_id"] = list_id
        out["appointment_list_name"] = list_name if list_id else DEFAULT_APPOINTMENT_LIST_NAME

        try:
            from app.services.hubspot_connection_service import _ensure_access_token

            token = _ensure_access_token(db, org_id)
            eligible = search_contacts_with_appointment_date(
                token,
                date_prop,
                ["firstname", "lastname", "email", "phone", name_prop, phone_prop, date_prop],
                max_results=5000,
            )
            out["eligible_contacts"] = len(eligible)
        except HubspotListError as exc:
            out["message"] = str(exc)[:240]
            return out

        if out["eligible_contacts"] > 0:
            out["ready"] = True
            out["message"] = (
                f"{out['eligible_contacts']} HubSpot contact(s) have phone + {date_prop}. "
                "Click Sync CRM to import them — list membership is handled automatically."
            )
        else:
            out["message"] = (
                f"No HubSpot contacts have both phone and {date_prop} set. "
                f"Add those fields on each contact in HubSpot, then click Sync CRM."
            )
        return out

    out["ready"] = True
    out["message"] = f"{provider.replace('_', ' ').title()} is connected. Click Sync CRM to pull appointments."
    return out


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
