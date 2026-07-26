"""Expo hybrid offer delivery — match visitor interest to a booth asset and send the link."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.expo import ExpoBoothAsset, ExpoLead
from app.services.expo.question_bank import (
    format_asset_list_message,
    pick_assets_for_interest,
    resolve_pick_reply,
)

__all__ = [
    "load_booth_assets",
    "asset_public_url",
    "asset_public_url_for_lead",
    "deliver_asset_link_message",
    "mark_lead_offer_sent",
    "mark_lead_asset_opened",
    "lead_assets_sent_list",
    "lead_assets_opened_list",
    "pick_assets_for_interest",
    "format_asset_list_message",
    "resolve_pick_reply",
    "normalize_asset_purpose",
]

ASSET_PURPOSES = frozenset({"catalogue", "price_list", "product", "product_sheet", "other"})


def normalize_asset_purpose(raw: Any) -> str:
    clean = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if clean in {"catalog", "catalogue", "brochure"}:
        return "catalogue"
    if clean in {"price", "prices", "pricing", "pricelist", "price_list"}:
        return "price_list"
    if clean in {"product_sheet", "sheet", "datasheet", "data_sheet", "spec", "specs"}:
        return "product_sheet"
    if clean in {"other", "misc"}:
        return "other"
    if clean in ASSET_PURPOSES:
        return clean
    return "product"


def load_booth_assets(db: Session, booth_id: str) -> list[dict[str, Any]]:
    from app.models.expo import ExpoBoothCategory, ExpoBoothProduct

    rows = db.execute(
        select(ExpoBoothAsset)
        .where(ExpoBoothAsset.booth_id == booth_id)
        .order_by(ExpoBoothAsset.sort_order.asc())
    ).scalars().all()

    product_ids = {str(getattr(a, "product_id", None) or "") for a in rows if getattr(a, "product_id", None)}
    products_by_id: dict[str, ExpoBoothProduct] = {}
    categories_by_id: dict[str, ExpoBoothCategory] = {}
    if product_ids:
        products = db.execute(
            select(ExpoBoothProduct).where(ExpoBoothProduct.id.in_(list(product_ids)))
        ).scalars().all()
        products_by_id = {p.id: p for p in products}
        cat_ids = {str(p.category_id) for p in products if p.category_id}
        if cat_ids:
            cats = db.execute(
                select(ExpoBoothCategory).where(ExpoBoothCategory.id.in_(list(cat_ids)))
            ).scalars().all()
            categories_by_id = {c.id: c for c in cats}

    out: list[dict[str, Any]] = []
    for a in rows:
        product = products_by_id.get(str(getattr(a, "product_id", None) or ""))
        category = categories_by_id.get(str(product.category_id)) if product is not None else None
        out.append(
            {
                "id": a.id,
                "product_id": getattr(a, "product_id", None),
                "asset_key": a.asset_key,
                "title": a.title,
                "short_description": a.short_description,
                "kind": a.kind,
                "purpose": normalize_asset_purpose(getattr(a, "purpose", None) or "product"),
                "external_url": a.external_url,
                "storage_path": a.storage_path,
                "match_keywords": a.match_keywords,
                "is_default": a.is_default,
                "sort_order": a.sort_order,
                "product_name": (product.name if product is not None else "") or "",
                "category_name": (category.name if category is not None else "") or "",
                "category_id": (category.id if category is not None else None),
            }
        )
    return out


def asset_public_url(asset: dict[str, Any], booth_token: str, *, lead_id: str | None = None) -> str:
    """Absolute HTTPS link visitors can open in WhatsApp / web (never a relative path)."""
    external = str(asset.get("external_url") or "").strip()
    if external and not lead_id:
        # External URLs skip open-tracking unless we proxy — still return them for delivery.
        if external.startswith("http://") or external.startswith("https://"):
            return external
        return f"https://{external.lstrip('/')}"

    from app.services.brand_assets import api_public_origin

    api = api_public_origin().rstrip("/")
    asset_id = str(asset.get("id") or "").strip()
    token = str(booth_token or "").strip()
    path = f"/public/expo/assets/{token}/{asset_id}"
    if lead_id:
        path = f"{path}?lead_id={lead_id}"
    return f"{api}{path}" if api else f"https://api.voxbulk.com{path}"


def asset_public_url_for_lead(asset: dict[str, Any], booth_token: str, lead_id: str) -> str:
    return asset_public_url(asset, booth_token, lead_id=lead_id)


def deliver_asset_link_message(asset: dict[str, Any], booth_token: str, *, lead_id: str | None = None) -> str:
    title = str(asset.get("title") or "our info pack").strip()
    desc = str(asset.get("short_description") or "").strip()
    url = asset_public_url(asset, booth_token, lead_id=lead_id)
    lines = [f"Here you go — {title}"]
    if desc:
        lines.append(desc)
    lines.append(url)
    return "\n".join(lines)


def lead_assets_sent_list(lead: ExpoLead) -> list[Any]:
    try:
        sent = json.loads(lead.assets_sent_json or "[]")
        return sent if isinstance(sent, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def lead_assets_opened_list(lead: ExpoLead) -> list[dict[str, Any]]:
    try:
        opened = json.loads(lead.assets_opened_json or "[]")
        return opened if isinstance(opened, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def mark_lead_offer_sent(db: Session, lead: ExpoLead, asset: dict[str, Any]) -> None:
    sent = lead_assets_sent_list(lead)
    key = str(asset.get("asset_key") or asset.get("id") or "").strip()
    entry = {
        "asset_id": str(asset.get("id") or ""),
        "asset_key": key,
        "purpose": normalize_asset_purpose(asset.get("purpose")),
        "title": str(asset.get("title") or ""),
        "sent_at": datetime.utcnow().isoformat(),
    }
    # Support legacy string lists and new object lists.
    existing_keys = set()
    for item in sent:
        if isinstance(item, str):
            existing_keys.add(item)
        elif isinstance(item, dict):
            existing_keys.add(str(item.get("asset_key") or item.get("asset_id") or ""))
    if key and key not in existing_keys:
        sent.append(entry)
    lead.assets_sent_json = json.dumps(sent)
    lead.offer_sent_at = datetime.utcnow()
    lead.updated_at = datetime.utcnow()
    db.add(lead)


def mark_lead_asset_opened(
    db: Session,
    *,
    lead: ExpoLead,
    asset: ExpoBoothAsset | dict[str, Any],
) -> bool:
    """Record first open/download for an asset. Returns True if newly recorded."""
    if isinstance(asset, dict):
        asset_id = str(asset.get("id") or "").strip()
        asset_key = str(asset.get("asset_key") or asset_id).strip()
        purpose = normalize_asset_purpose(asset.get("purpose"))
        title = str(asset.get("title") or "")
    else:
        asset_id = str(asset.id or "").strip()
        asset_key = str(asset.asset_key or asset_id).strip()
        purpose = normalize_asset_purpose(getattr(asset, "purpose", None))
        title = str(asset.title or "")
    if not asset_id and not asset_key:
        return False
    opened = lead_assets_opened_list(lead)
    for item in opened:
        if not isinstance(item, dict):
            continue
        if str(item.get("asset_id") or "") == asset_id or str(item.get("asset_key") or "") == asset_key:
            return False
    opened.append(
        {
            "asset_id": asset_id,
            "asset_key": asset_key,
            "purpose": purpose,
            "title": title,
            "opened_at": datetime.utcnow().isoformat(),
        }
    )
    lead.assets_opened_json = json.dumps(opened)
    lead.updated_at = datetime.utcnow()
    db.add(lead)
    return True
