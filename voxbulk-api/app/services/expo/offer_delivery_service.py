"""Expo hybrid offer delivery — match visitor interest to a booth asset and send the link."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.expo import ExpoBoothAsset, ExpoLead
from app.services.expo.question_bank import (
    format_asset_list_message,
    pick_assets_for_interest,
    resolve_pick_reply,
)

__all__ = [
    "load_booth_assets",
    "asset_public_url",
    "deliver_asset_link_message",
    "mark_lead_offer_sent",
    "pick_assets_for_interest",
    "format_asset_list_message",
    "resolve_pick_reply",
]


def load_booth_assets(db: Session, booth_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        select(ExpoBoothAsset)
        .where(ExpoBoothAsset.booth_id == booth_id)
        .order_by(ExpoBoothAsset.sort_order.asc())
    ).scalars().all()
    return [
        {
            "id": a.id,
            "asset_key": a.asset_key,
            "title": a.title,
            "short_description": a.short_description,
            "kind": a.kind,
            "external_url": a.external_url,
            "storage_path": a.storage_path,
            "match_keywords": a.match_keywords,
            "is_default": a.is_default,
            "sort_order": a.sort_order,
        }
        for a in rows
    ]


def asset_public_url(asset: dict[str, Any], booth_token: str) -> str:
    external = str(asset.get("external_url") or "").strip()
    if external:
        return external
    settings = get_settings()
    api = str(
        getattr(settings, "public_api_base_url", None) or getattr(settings, "api_public_origin", "") or ""
    ).rstrip("/")
    path = f"/public/expo/assets/{booth_token}/{asset.get('id')}"
    return f"{api}{path}" if api else path


def deliver_asset_link_message(asset: dict[str, Any], booth_token: str) -> str:
    title = str(asset.get("title") or "our info pack").strip()
    desc = str(asset.get("short_description") or "").strip()
    url = asset_public_url(asset, booth_token)
    lines = [f"Here you go — {title}"]
    if desc:
        lines.append(desc)
    lines.append(url)
    return "\n".join(lines)


def mark_lead_offer_sent(db: Session, lead: ExpoLead, asset: dict[str, Any]) -> None:
    try:
        sent = json.loads(lead.assets_sent_json or "[]")
        if not isinstance(sent, list):
            sent = []
    except (json.JSONDecodeError, TypeError):
        sent = []
    key = str(asset.get("asset_key") or asset.get("id") or "").strip()
    if key and key not in sent:
        sent.append(key)
    lead.assets_sent_json = json.dumps(sent)
    lead.offer_sent_at = datetime.utcnow()
    lead.updated_at = datetime.utcnow()
    db.add(lead)
