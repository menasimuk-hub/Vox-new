"""Shared CRM connection helpers — one active CRM per organisation."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.encryption import get_encryptor
from app.models.organisation import Organisation
from app.services.crm_providers import CRM_CONFIG_COLUMNS, CRM_PROVIDERS, crm_provider_label


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def encrypt_token(value: str) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    if token.startswith("enc:"):
        return token
    return "enc:" + get_encryptor().encrypt_str(token)


def decrypt_token(value: str) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    if token.startswith("enc:"):
        try:
            return get_encryptor().decrypt_str(token[4:])
        except Exception:
            return ""
    return token


def get_crm_config_raw(db: Session, org_id: str, provider: str) -> dict[str, Any]:
    column = CRM_CONFIG_COLUMNS.get(str(provider or "").strip().lower())
    if not column:
        return {}
    org = db.get(Organisation, org_id)
    if org is None:
        return {}
    cfg = _loads(getattr(org, column, None))
    for key in ("access_token", "refresh_token"):
        if key in cfg:
            cfg[key] = decrypt_token(str(cfg.get(key) or ""))
    return cfg


def save_crm_config_raw(db: Session, org_id: str, provider: str, payload: dict[str, Any]) -> None:
    column = CRM_CONFIG_COLUMNS.get(str(provider or "").strip().lower())
    if not column:
        raise ValueError(f"Unsupported CRM provider: {provider}")
    org = db.get(Organisation, org_id)
    if org is None:
        raise ValueError("Organisation not found")
    cfg = dict(payload)
    for key in ("access_token", "refresh_token"):
        if key in cfg:
            cfg[key] = encrypt_token(str(cfg.get(key) or ""))
    setattr(org, column, json.dumps(cfg, ensure_ascii=False))
    db.add(org)
    db.commit()


def active_crm_provider(db: Session, org_id: str) -> str | None:
    org = db.get(Organisation, org_id)
    if org is None:
        return None
    for provider in CRM_PROVIDERS:
        column = CRM_CONFIG_COLUMNS[provider]
        cfg = _loads(getattr(org, column, None))
        token = decrypt_token(str(cfg.get("access_token") or ""))
        if token:
            return provider
    return None


def ensure_can_connect_crm(db: Session | None, org_id: str, provider: str, *, replace: bool = False) -> None:
    if db is None:
        return
    wanted = str(provider or "").strip().lower()
    if wanted not in CRM_PROVIDERS:
        raise ValueError(f"Unsupported CRM provider: {provider}")
    current = active_crm_provider(db, org_id)
    if not current or current == wanted:
        return
    if replace:
        disconnect_crm(db, org_id, provider=current)
        return
    current_label = crm_provider_label(current) or current
    raise ValueError(f"Disconnect {current_label} first or switch CRM from Settings → Integrations")


def disconnect_crm(db: Session, org_id: str, *, provider: str | None = None) -> dict[str, Any]:
    org = db.get(Organisation, org_id)
    if org is None:
        raise ValueError("Organisation not found")
    current = active_crm_provider(db, org_id)
    if not current:
        return crm_status_summary(db, org_id)
    if provider:
        wanted = str(provider).strip().lower()
        if wanted != current:
            raise ValueError(f"Not connected to {provider}")
    column = CRM_CONFIG_COLUMNS[current]
    setattr(org, column, None)
    # Booking (HubSpot Meetings / Zoho Bookings) can stand alone via pasted URL —
    # do not clear scheduling when CRM is disconnected.
    db.add(org)
    db.commit()
    return crm_status_summary(db, org_id)


def crm_status_summary(db: Session, org_id: str) -> dict[str, Any]:
    active = active_crm_provider(db, org_id)
    return {
        "active_crm_provider": active,
        "active_crm_label": crm_provider_label(active),
    }


def crm_connected(db: Session, org_id: str, provider: str) -> bool:
    return active_crm_provider(db, org_id) == str(provider or "").strip().lower()
