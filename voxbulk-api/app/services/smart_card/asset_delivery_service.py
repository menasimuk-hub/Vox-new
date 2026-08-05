"""Smart Card catalogue delivery — public asset URLs, WhatsApp documents, email attachments.

Mirrors the Expo contract: visitors always receive a public tracked URL, and the same rows
are recorded on the lead so the dashboard can show what was sent and what was opened.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.smart_card import SmartCardAsset, SmartCardLead, SmartCardProduct
from app.services.smart_card.asset_storage_service import resolve_storage_abs_path

logger = logging.getLogger(__name__)

# Attachments above this size stay as links only — mail servers reject large payloads.
MAX_EMAIL_ATTACHMENT_BYTES = 8 * 1024 * 1024

_DOCUMENT_SUFFIX_MEDIA = {
    ".pdf": ("application", "pdf"),
    ".xls": ("application", "vnd.ms-excel"),
    ".xlsx": ("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".csv": ("text", "csv"),
    ".doc": ("application", "msword"),
    ".docx": ("application", "vnd.openxmlformats-officedocument.wordprocessingml.document"),
}


def load_assets_for_products(
    db: Session,
    *,
    org_id: str,
    product_ids: list[str],
) -> list[dict[str, Any]]:
    """Assets attached to the chosen products, plus assets pinned to their categories."""
    wanted = [str(p).strip() for p in product_ids if str(p or "").strip()]
    if not wanted:
        return []

    products = (
        db.execute(
            select(SmartCardProduct).where(
                SmartCardProduct.id.in_(wanted),
                SmartCardProduct.org_id == org_id,
            )
        )
        .scalars()
        .all()
    )
    if not products:
        return []
    product_names = {str(p.id): str(p.name or "") for p in products}
    category_ids = {str(p.category_id) for p in products if p.category_id}

    rows = (
        db.execute(
            select(SmartCardAsset)
            .where(
                SmartCardAsset.org_id == org_id,
                (SmartCardAsset.product_id.in_(wanted))
                | (
                    SmartCardAsset.product_id.is_(None)
                    & SmartCardAsset.category_id.in_(category_ids or {"__none__"})
                ),
            )
            .order_by(SmartCardAsset.sort_order.asc(), SmartCardAsset.title.asc())
        )
        .scalars()
        .all()
    )

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for a in rows:
        aid = str(a.id)
        if aid in seen:
            continue
        seen.add(aid)
        out.append(
            {
                "id": aid,
                "product_id": a.product_id,
                "product_name": product_names.get(str(a.product_id or ""), ""),
                "title": str(a.title or "Document"),
                "kind": str(a.kind or "pdf"),
                "purpose": str(a.purpose or "catalogue"),
                "storage_path": a.storage_path,
                "external_url": a.external_url,
                "original_filename": a.original_filename,
            }
        )
    return out


def asset_public_url(asset: dict[str, Any], qr_token: str, *, lead_id: str | None = None) -> str:
    """Absolute HTTPS link a visitor can open from WhatsApp, web or email."""
    external = str(asset.get("external_url") or "").strip()
    if external and not lead_id:
        if external.startswith("http://") or external.startswith("https://"):
            return external
        return f"https://{external.lstrip('/')}"

    from app.services.brand_assets import api_public_origin

    api = (api_public_origin() or "").rstrip("/") or "https://api.voxbulk.com"
    path = f"/public/smart-card/{str(qr_token or '').strip()}/assets/{str(asset.get('id') or '').strip()}"
    if lead_id:
        path = f"{path}?lead_id={lead_id}"
    return f"{api}{path}"


def asset_filename(asset: dict[str, Any]) -> str:
    original = str(asset.get("original_filename") or "").strip()
    if original:
        return Path(original).name[:240]
    title = str(asset.get("title") or "document").strip() or "document"
    suffix = Path(str(asset.get("storage_path") or "")).suffix.lower() or ".pdf"
    return f"{title[:200]}{suffix}"


def supports_document_send(asset: dict[str, Any]) -> bool:
    """WhatsApp document messages only accept file-like assets we can name."""
    suffix = Path(str(asset.get("storage_path") or asset.get("original_filename") or "")).suffix.lower()
    if suffix in _DOCUMENT_SUFFIX_MEDIA:
        return True
    return str(asset.get("kind") or "").strip().lower() in {"pdf", "document", "spreadsheet"}


def build_delivery_rows(
    db: Session,
    *,
    org_id: str,
    qr_token: str,
    lead_id: str | None,
    product_ids: list[str],
) -> list[dict[str, Any]]:
    """Assets ready to send: id, title, public URL and download filename."""
    assets = load_assets_for_products(db, org_id=org_id, product_ids=product_ids)
    for asset in assets:
        asset["url"] = asset_public_url(asset, qr_token, lead_id=lead_id)
        asset["filename"] = asset_filename(asset)
    return assets


def email_attachments(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Read stored files into SMTP attachment dicts; oversized/external assets stay link-only."""
    out: list[dict[str, Any]] = []
    for asset in assets:
        abs_path = resolve_storage_abs_path(asset.get("storage_path"))
        if abs_path is None:
            continue
        try:
            if abs_path.stat().st_size > MAX_EMAIL_ATTACHMENT_BYTES:
                logger.info("smart_card_asset_too_large_for_email asset=%s", asset.get("id"))
                continue
            content = abs_path.read_bytes()
        except OSError:
            logger.warning("smart_card_asset_read_failed asset=%s", asset.get("id"), exc_info=True)
            continue
        maintype, subtype = _DOCUMENT_SUFFIX_MEDIA.get(
            abs_path.suffix.lower(), ("application", "octet-stream")
        )
        out.append(
            {
                "filename": asset.get("filename") or abs_path.name,
                "content": content,
                "maintype": maintype,
                "subtype": subtype,
            }
        )
    return out


def _lead_payload(lead: SmartCardLead) -> dict[str, Any]:
    try:
        parsed = json.loads(lead.assets_sent_json or "{}")
    except (json.JSONDecodeError, TypeError):
        parsed = {}
    return parsed if isinstance(parsed, dict) else {}


def mark_lead_assets_sent(db: Session, *, lead: SmartCardLead, assets: list[dict[str, Any]]) -> None:
    if not assets:
        return
    payload = _lead_payload(lead)
    sent = payload.get("assets") if isinstance(payload.get("assets"), list) else []
    known = {str(item.get("asset_id")) for item in sent if isinstance(item, dict)}
    now = datetime.utcnow().isoformat()
    for asset in assets:
        aid = str(asset.get("id") or "")
        if not aid or aid in known:
            continue
        known.add(aid)
        sent.append(
            {
                "asset_id": aid,
                "title": asset.get("title"),
                "purpose": asset.get("purpose"),
                "sent_at": now,
            }
        )
    payload["assets"] = sent
    lead.assets_sent_json = json.dumps(payload, ensure_ascii=False)
    db.add(lead)


def mark_lead_asset_opened(db: Session, *, lead: SmartCardLead, asset_id: str) -> bool:
    """Record the first open of an asset. Returns True when this was a new open."""
    payload = _lead_payload(lead)
    opened = payload.get("assets_opened") if isinstance(payload.get("assets_opened"), list) else []
    known = {str(item.get("asset_id")) for item in opened if isinstance(item, dict)}
    aid = str(asset_id or "").strip()
    if not aid or aid in known:
        return False
    opened.append({"asset_id": aid, "opened_at": datetime.utcnow().isoformat()})
    payload["assets_opened"] = opened
    lead.assets_sent_json = json.dumps(payload, ensure_ascii=False)
    db.add(lead)
    return True
