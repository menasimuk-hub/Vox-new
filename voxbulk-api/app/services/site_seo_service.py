"""SEO Control: settings, content SEO, redirects, sitemap, health, IndexNow."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
import uuid
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.encryption import get_encryptor
from app.models.faq import FAQItem
from app.models.site_blog_news_item import SiteBlogNewsItem
from app.models.site_seo import SiteSeoHealthSnapshot, SiteSeoRedirect, SiteSeoSettings

SITE_ORIGIN = "https://voxbulk.com"
KIND_BLOG = "blog"
KIND_NEWS = "news"
KIND_FAQ = "faq"
KINDS = frozenset({KIND_BLOG, KIND_NEWS, KIND_FAQ})
PATH_PREFIX = {KIND_BLOG: "/blog/", KIND_NEWS: "/news/", KIND_FAQ: "/faq/"}
ROBOTS_INDEX = "index,follow"
ROBOTS_NOINDEX = "noindex"
ROBOTS_NOFOLLOW = "index,nofollow"
DEFAULT_ROBOTS = """User-agent: *
Allow: /
Disallow: /onboarding
Disallow: /signin

Sitemap: https://voxbulk.com/sitemap.xml
"""

_SLUG_RE = re.compile(r"[^a-z0-9]+")
STATIC_SITEMAP_PATHS = [
    "/",
    "/recruitment",
    "/surveys",
    "/feedback",
    "/pricing",
    "/contact",
    "/blog",
    "/news",
    "/faq",
    "/legal-policies",
    "/privacy",
    "/terms",
    "/cookies",
    "/gdpr",
    "/legal",
]


def slugify(title: str) -> str:
    base = _SLUG_RE.sub("-", (title or "").strip().lower()).strip("-")
    return (base or "item")[:160]


def _encrypt(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    return "enc:" + get_encryptor().encrypt_str(raw)


def _decrypt(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.startswith("enc:"):
        try:
            return get_encryptor().decrypt_str(raw[4:])
        except Exception:
            return ""
    return raw


def _normalize_path(path: str) -> str:
    p = (path or "").strip()
    if not p.startswith("/"):
        p = "/" + p
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/")
    return p


def _derive_index_status(robots: str, *, visible: bool = True) -> str:
    if not visible:
        return "excluded"
    r = (robots or ROBOTS_INDEX).lower()
    if "noindex" in r:
        return "excluded"
    return "pending"


_DEFAULT_HOME_TITLE = "VoxBulk | WhatsApp Surveys, AI Interviews & Voice Agents for Business"
_DEFAULT_HOME_DESCRIPTION = (
    "Run WhatsApp surveys, QR customer feedback, and AI phone interviews from one UK-built platform. "
    "Multilingual replies, scored interviews, and live dashboards — cancel anytime."
)
_DEFAULT_HOME_FOCUS = "whatsapp survey software"
_DEFAULT_HOME_TAGS = (
    "ai interview platform, customer feedback whatsapp, voice ai agents, "
    "recruitment automation uk, qr code feedback, multilingual surveys"
)


def ensure_settings(db: Session) -> SiteSeoSettings:
    row = db.execute(select(SiteSeoSettings).where(SiteSeoSettings.id == "default")).scalar_one_or_none()
    if row:
        # Fill empty homepage SEO only — never overwrite Admin-saved copy.
        dirty = False
        if not str(row.home_title or "").strip():
            row.home_title = _DEFAULT_HOME_TITLE
            dirty = True
        if not str(row.home_description or "").strip():
            row.home_description = _DEFAULT_HOME_DESCRIPTION
            dirty = True
        if not str(row.default_meta_description or "").strip():
            row.default_meta_description = _DEFAULT_HOME_DESCRIPTION
            dirty = True
        if not str(row.home_focus_keyword or "").strip():
            row.home_focus_keyword = _DEFAULT_HOME_FOCUS
            dirty = True
        if not str(row.home_tags or "").strip():
            row.home_tags = _DEFAULT_HOME_TAGS
            dirty = True
        if dirty:
            row.updated_at = datetime.utcnow()
            db.add(row)
            db.commit()
            db.refresh(row)
        return row
    row = SiteSeoSettings(
        id="default",
        default_meta_description=_DEFAULT_HOME_DESCRIPTION,
        home_title=_DEFAULT_HOME_TITLE,
        home_description=_DEFAULT_HOME_DESCRIPTION,
        home_focus_keyword=_DEFAULT_HOME_FOCUS,
        home_tags=_DEFAULT_HOME_TAGS,
        robots_txt=DEFAULT_ROBOTS,
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    snap = db.execute(
        select(SiteSeoHealthSnapshot).where(SiteSeoHealthSnapshot.id == "latest")
    ).scalar_one_or_none()
    if snap is None:
        db.add(
            SiteSeoHealthSnapshot(
                id="latest",
                mobile_note="",
                broken_links_json="[]",
                structured_data_json="{}",
                updated_at=datetime.utcnow(),
            )
        )
    db.commit()
    db.refresh(row)
    return row


def ensure_health(db: Session) -> SiteSeoHealthSnapshot:
    row = db.execute(
        select(SiteSeoHealthSnapshot).where(SiteSeoHealthSnapshot.id == "latest")
    ).scalar_one_or_none()
    if row:
        return row
    row = SiteSeoHealthSnapshot(
        id="latest",
        mobile_note="",
        broken_links_json="[]",
        structured_data_json="{}",
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def settings_to_admin(row: SiteSeoSettings) -> dict[str, Any]:
    return {
        "site_name": row.site_name,
        "title_template": row.title_template,
        "default_meta_description": row.default_meta_description or "",
        "default_social_image_url": row.default_social_image_url,
        "home_title": row.home_title or "",
        "home_description": row.home_description or "",
        "home_focus_keyword": row.home_focus_keyword or "",
        "home_tags": row.home_tags or "",
        "schema_organization": bool(row.schema_organization),
        "schema_website": bool(row.schema_website),
        "schema_breadcrumbs": bool(row.schema_breadcrumbs),
        "schema_content": bool(row.schema_content),
        "google_site_verification": row.google_site_verification or "",
        "google_analytics_id": row.google_analytics_id or "",
        "meta_pixel_id": row.meta_pixel_id or "",
        "linkedin_partner_id": row.linkedin_partner_id or "",
        "google_ads_id": row.google_ads_id or "",
        "x_pixel_id": row.x_pixel_id or "",
        "tiktok_pixel_id": row.tiktok_pixel_id or "",
        "pinterest_tag_id": row.pinterest_tag_id or "",
        "google_news_enabled": bool(row.google_news_enabled),
        "google_news_publication": row.google_news_publication or "",
        "google_news_language": row.google_news_language or "en",
        "gsc_property_url": row.gsc_property_url or "",
        "psi_api_key_set": bool(_decrypt(row.psi_api_key_encrypted)),
        "moz_access_id_set": bool(_decrypt(row.moz_access_id_encrypted)),
        "moz_secret_key_set": bool(_decrypt(row.moz_secret_key_encrypted)),
        "indexnow_key": row.indexnow_key or "",
        "indexnow_last_pinged_at": row.indexnow_last_pinged_at.isoformat() if row.indexnow_last_pinged_at else None,
        "robots_txt": row.robots_txt or DEFAULT_ROBOTS,
        "sitemap_last_generated_at": row.sitemap_last_generated_at.isoformat() if row.sitemap_last_generated_at else None,
        "sitemap_last_submitted_at": row.sitemap_last_submitted_at.isoformat() if row.sitemap_last_submitted_at else None,
        "connections": {
            "gsc": bool(row.gsc_connected),
            "psi": bool(row.psi_connected),
            "moz": bool(row.moz_connected),
        },
        "gsc_oauth_configured": False,  # filled by router/settings loader when db available
        "gsc_avg_position": row.gsc_avg_position,
        "gsc_avg_position_prev": row.gsc_avg_position_prev,
        "moz_domain_authority": row.moz_domain_authority,
        "moz_domain_authority_prev": row.moz_domain_authority_prev,
    }


def settings_to_admin_with_oauth(db: Session, row: SiteSeoSettings) -> dict[str, Any]:
    from app.services.gsc_oauth_service import gsc_oauth_configured

    data = settings_to_admin(row)
    data["gsc_oauth_configured"] = gsc_oauth_configured(db)
    return data


def settings_to_public(row: SiteSeoSettings) -> dict[str, Any]:
    return {
        "site_name": row.site_name,
        "title_template": row.title_template,
        "default_meta_description": row.default_meta_description or "",
        "default_social_image_url": row.default_social_image_url,
        "home_title": row.home_title or "",
        "home_description": row.home_description or "",
        "home_focus_keyword": row.home_focus_keyword or "",
        "home_tags": row.home_tags or "",
        "schema_organization": bool(row.schema_organization),
        "schema_website": bool(row.schema_website),
        "schema_breadcrumbs": bool(row.schema_breadcrumbs),
        "schema_content": bool(row.schema_content),
        "google_site_verification": row.google_site_verification or "",
        "google_analytics_id": row.google_analytics_id or "",
        "meta_pixel_id": row.meta_pixel_id or "",
        "linkedin_partner_id": row.linkedin_partner_id or "",
        "google_ads_id": row.google_ads_id or "",
        "x_pixel_id": row.x_pixel_id or "",
        "tiktok_pixel_id": row.tiktok_pixel_id or "",
        "pinterest_tag_id": row.pinterest_tag_id or "",
        "google_news_enabled": bool(row.google_news_enabled),
        "google_news_publication": row.google_news_publication or "",
        "google_news_language": row.google_news_language or "en",
        "indexnow_key": row.indexnow_key or "",
        "robots_txt": row.robots_txt or DEFAULT_ROBOTS,
    }


def update_settings(db: Session, payload: dict[str, Any]) -> SiteSeoSettings:
    row = ensure_settings(db)
    str_fields = [
        "site_name",
        "title_template",
        "default_meta_description",
        "home_title",
        "home_description",
        "home_focus_keyword",
        "home_tags",
        "google_site_verification",
        "google_analytics_id",
        "meta_pixel_id",
        "linkedin_partner_id",
        "google_ads_id",
        "x_pixel_id",
        "tiktok_pixel_id",
        "pinterest_tag_id",
        "google_news_publication",
        "google_news_language",
        "gsc_property_url",
        "robots_txt",
    ]
    for f in str_fields:
        if f in payload:
            setattr(row, f, str(payload.get(f) or ""))
    if "default_social_image_url" in payload:
        row.default_social_image_url = payload.get("default_social_image_url") or None
    for f in ("schema_organization", "schema_website", "schema_breadcrumbs", "schema_content", "google_news_enabled"):
        if f in payload:
            setattr(row, f, bool(payload.get(f)))
    if payload.get("psi_api_key"):
        row.psi_api_key_encrypted = _encrypt(str(payload["psi_api_key"]))
    if payload.get("moz_access_id"):
        row.moz_access_id_encrypted = _encrypt(str(payload["moz_access_id"]))
    if payload.get("moz_secret_key"):
        row.moz_secret_key_encrypted = _encrypt(str(payload["moz_secret_key"]))
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def _blog_row_to_seo(row: SiteBlogNewsItem) -> dict[str, Any]:
    prefix = PATH_PREFIX[row.kind]
    path = f"{prefix}{row.slug}"
    return {
        "id": row.id,
        "kind": row.kind,
        "title": row.title,
        "slug": row.slug,
        "path": path,
        "url": f"{SITE_ORIGIN}{path}",
        "meta_title": row.meta_title or row.title,
        "meta_description": row.meta_description or row.excerpt or "",
        "canonical_url": row.canonical_url or "",
        "robots": row.robots or ROBOTS_INDEX,
        "focus_keyword": row.focus_keyword or "",
        "tags": row.tags or "",
        "author": row.author or "",
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "last_updated": (row.seo_updated_at or row.updated_at).isoformat() if (row.seo_updated_at or row.updated_at) else None,
        "social_title": row.social_title or "",
        "social_description": row.social_description or "",
        "social_image_url": row.social_image_url or row.image_url,
        "index_status": row.index_status or _derive_index_status(row.robots, visible=row.is_visible),
        "index_requested_at": row.index_requested_at.isoformat() if row.index_requested_at else None,
        "is_visible": bool(row.is_visible),
        "excerpt": row.excerpt or "",
    }


def _faq_row_to_seo(row: FAQItem) -> dict[str, Any]:
    path = f"/faq/{row.slug}"
    return {
        "id": str(row.id),
        "kind": KIND_FAQ,
        "title": row.question,
        "question": row.question,
        "answer": row.answer,
        "slug": row.slug,
        "path": path,
        "url": f"{SITE_ORIGIN}{path}",
        "meta_title": row.meta_title or row.question,
        "meta_description": row.meta_description or "",
        "canonical_url": row.canonical_url or "",
        "robots": row.robots or ROBOTS_INDEX,
        "focus_keyword": row.focus_keyword or "",
        "tags": row.tags or "",
        "author": row.author or "",
        "published_at": (row.published_at or row.created_at).isoformat() if (row.published_at or row.created_at) else None,
        "last_updated": (row.seo_updated_at or row.updated_at).isoformat() if (row.seo_updated_at or row.updated_at) else None,
        "social_title": row.social_title or "",
        "social_description": row.social_description or "",
        "social_image_url": row.social_image_url,
        "index_status": row.index_status or _derive_index_status(row.robots, visible=row.is_published),
        "index_requested_at": row.index_requested_at.isoformat() if row.index_requested_at else None,
        "is_visible": bool(row.is_published),
    }


def list_content(db: Session, kind: str) -> list[dict[str, Any]]:
    k = (kind or "").strip().lower()
    if k not in KINDS:
        raise HTTPException(status_code=400, detail="kind must be blog, news, or faq")
    if k == KIND_FAQ:
        rows = db.execute(select(FAQItem).order_by(FAQItem.sort_order.asc(), FAQItem.id.desc())).scalars().all()
        return [_faq_row_to_seo(r) for r in rows]
    rows = (
        db.execute(
            select(SiteBlogNewsItem)
            .where(SiteBlogNewsItem.kind == k)
            .order_by(SiteBlogNewsItem.published_at.desc())
        )
        .scalars()
        .all()
    )
    return [_blog_row_to_seo(r) for r in rows]


def overview(db: Session) -> dict[str, Any]:
    settings = ensure_settings(db)
    blog = list_content(db, KIND_BLOG)
    news = list_content(db, KIND_NEWS)
    faq = list_content(db, KIND_FAQ)
    all_items = blog + news + faq

    def counts(items: list[dict[str, Any]]) -> dict[str, int]:
        out = {"total": len(items), "indexed": 0, "pending": 0, "excluded": 0}
        for it in items:
            st = it.get("index_status") or "pending"
            if st in out:
                out[st] += 1
            else:
                out["pending"] += 1
        return out

    ranking = None
    trust = None
    if settings.gsc_connected and settings.gsc_avg_position is not None:
        ranking = {
            "current": float(settings.gsc_avg_position),
            "previous": float(settings.gsc_avg_position_prev or settings.gsc_avg_position),
            "connected": True,
        }
    else:
        ranking = {"current": None, "previous": None, "connected": False}
    if settings.moz_connected and settings.moz_domain_authority is not None:
        trust = {
            "current": float(settings.moz_domain_authority),
            "previous": float(settings.moz_domain_authority_prev or settings.moz_domain_authority),
            "connected": True,
        }
    else:
        trust = {"current": None, "previous": None, "connected": False}

    return {
        "total_pages": len(all_items),
        "by_kind": {
            "blog": counts(blog),
            "news": counts(news),
            "faq": counts(faq),
        },
        "ranking": ranking,
        "trust": trust,
        "sitemap_last_submitted_at": settings.sitemap_last_submitted_at.isoformat()
        if settings.sitemap_last_submitted_at
        else None,
        "connections": {
            "gsc": bool(settings.gsc_connected),
            "psi": bool(settings.psi_connected),
            "moz": bool(settings.moz_connected),
        },
    }


def _get_blog(db: Session, item_id: str) -> SiteBlogNewsItem:
    row = db.execute(select(SiteBlogNewsItem).where(SiteBlogNewsItem.id == item_id)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")
    return row


def _get_faq(db: Session, item_id: str | int) -> FAQItem:
    try:
        iid = int(item_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Item not found") from exc
    row = db.execute(select(FAQItem).where(FAQItem.id == iid)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")
    return row


def _unique_content_slug(db: Session, kind: str, desired: str, *, exclude_id: str | int | None = None) -> str:
    base = slugify(desired)
    candidate = base
    n = 2
    while True:
        if kind == KIND_FAQ:
            q = select(FAQItem.id).where(FAQItem.slug == candidate)
            if exclude_id is not None:
                q = q.where(FAQItem.id != int(exclude_id))
        else:
            q = select(SiteBlogNewsItem.id).where(
                SiteBlogNewsItem.kind == kind,
                SiteBlogNewsItem.slug == candidate,
            )
            if exclude_id is not None:
                q = q.where(SiteBlogNewsItem.id != str(exclude_id))
        if db.execute(q).scalar_one_or_none() is None:
            return candidate
        candidate = f"{base}-{n}"[:180]
        n += 1


def upsert_redirect(db: Session, from_path: str, to_path: str, *, status_code: int = 301, source: str = "manual") -> SiteSeoRedirect:
    frm = _normalize_path(from_path)
    to = _normalize_path(to_path)
    if frm == to:
        raise HTTPException(status_code=400, detail="From and to paths must differ")
    existing = db.execute(select(SiteSeoRedirect).where(SiteSeoRedirect.from_path == frm)).scalar_one_or_none()
    now = datetime.utcnow()
    if existing:
        existing.to_path = to
        existing.status_code = int(status_code)
        existing.source = source
        existing.updated_at = now
        db.commit()
        db.refresh(existing)
        return existing
    row = SiteSeoRedirect(
        id=str(uuid.uuid4()),
        from_path=frm,
        to_path=to,
        status_code=int(status_code),
        source=source,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_content_seo(db: Session, kind: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    k = kind.strip().lower()
    if k not in KINDS:
        raise HTTPException(status_code=400, detail="Invalid kind")
    now = datetime.utcnow()
    robots = str(payload.get("robots") or ROBOTS_INDEX)
    if robots not in {ROBOTS_INDEX, ROBOTS_NOINDEX, ROBOTS_NOFOLLOW, "noindex,follow", "noindex,nofollow"}:
        robots = ROBOTS_INDEX

    if k == KIND_FAQ:
        row = _get_faq(db, item_id)
        old_slug = row.slug
        new_slug = (payload.get("slug") or "").strip() or old_slug
        new_slug = _unique_content_slug(db, KIND_FAQ, new_slug, exclude_id=row.id)
        if new_slug != old_slug and old_slug:
            upsert_redirect(db, f"/faq/{old_slug}", f"/faq/{new_slug}", status_code=301, source="slug_change")
        row.slug = new_slug
        if "meta_title" in payload:
            row.meta_title = str(payload.get("meta_title") or "")[:300]
        if "meta_description" in payload:
            row.meta_description = str(payload.get("meta_description") or "")
        if "canonical_url" in payload:
            row.canonical_url = str(payload.get("canonical_url") or "")[:500]
        row.robots = robots
        if "focus_keyword" in payload:
            row.focus_keyword = str(payload.get("focus_keyword") or "")[:200]
        if "tags" in payload:
            row.tags = str(payload.get("tags") or "")[:500]
        if "author" in payload:
            row.author = str(payload.get("author") or "")[:120]
        if "social_title" in payload:
            row.social_title = str(payload.get("social_title") or "")[:300]
        if "social_description" in payload:
            row.social_description = str(payload.get("social_description") or "")
        if "social_image_url" in payload:
            row.social_image_url = payload.get("social_image_url") or None
        if payload.get("published_at"):
            try:
                row.published_at = datetime.fromisoformat(str(payload["published_at"])[:19])
            except ValueError:
                pass
        row.index_status = _derive_index_status(robots, visible=row.is_published)
        row.seo_updated_at = now
        row.updated_at = now
        db.commit()
        db.refresh(row)
        return _faq_row_to_seo(row)

    row = _get_blog(db, item_id)
    old_slug = row.slug
    new_slug = (payload.get("slug") or "").strip() or old_slug
    new_slug = _unique_content_slug(db, row.kind, new_slug, exclude_id=row.id)
    if new_slug != old_slug and old_slug:
        upsert_redirect(
            db,
            f"{PATH_PREFIX[row.kind]}{old_slug}",
            f"{PATH_PREFIX[row.kind]}{new_slug}",
            status_code=301,
            source="slug_change",
        )
    row.slug = new_slug
    if "meta_title" in payload:
        row.meta_title = str(payload.get("meta_title") or "")[:300]
    if "meta_description" in payload:
        row.meta_description = str(payload.get("meta_description") or "")
    if "canonical_url" in payload:
        row.canonical_url = str(payload.get("canonical_url") or "")[:500]
    row.robots = robots
    if "focus_keyword" in payload:
        row.focus_keyword = str(payload.get("focus_keyword") or "")[:200]
    if "tags" in payload:
        row.tags = str(payload.get("tags") or "")[:500]
    if "author" in payload:
        row.author = str(payload.get("author") or "")[:120]
    if "social_title" in payload:
        row.social_title = str(payload.get("social_title") or "")[:300]
    if "social_description" in payload:
        row.social_description = str(payload.get("social_description") or "")
    if "social_image_url" in payload:
        row.social_image_url = payload.get("social_image_url") or None
    if payload.get("published_at"):
        try:
            row.published_at = date.fromisoformat(str(payload["published_at"])[:10])
        except ValueError:
            pass
    row.index_status = _derive_index_status(robots, visible=row.is_visible)
    row.seo_updated_at = now
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return _blog_row_to_seo(row)


def toggle_index(db: Session, kind: str, item_id: str) -> dict[str, Any]:
    k = kind.strip().lower()
    if k == KIND_FAQ:
        row = _get_faq(db, item_id)
        if "noindex" in (row.robots or "").lower():
            row.robots = ROBOTS_INDEX
        else:
            row.robots = ROBOTS_NOINDEX
        row.index_status = _derive_index_status(row.robots, visible=row.is_published)
        row.seo_updated_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
        return _faq_row_to_seo(row)
    row = _get_blog(db, item_id)
    if "noindex" in (row.robots or "").lower():
        row.robots = ROBOTS_INDEX
    else:
        row.robots = ROBOTS_NOINDEX
    row.index_status = _derive_index_status(row.robots, visible=row.is_visible)
    row.seo_updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _blog_row_to_seo(row)


def request_indexing(db: Session, kind: str, item_id: str) -> dict[str, Any]:
    settings = ensure_settings(db)
    if kind.strip().lower() == KIND_FAQ:
        row = _get_faq(db, item_id)
        url = f"{SITE_ORIGIN}/faq/{row.slug}"
        row.index_requested_at = datetime.utcnow()
        if row.index_status != "excluded":
            row.index_status = "pending"
        db.commit()
        db.refresh(row)
        result = _faq_row_to_seo(row)
    else:
        row_b = _get_blog(db, item_id)
        url = f"{SITE_ORIGIN}{PATH_PREFIX[row_b.kind]}{row_b.slug}"
        row_b.index_requested_at = datetime.utcnow()
        if row_b.index_status != "excluded":
            row_b.index_status = "pending"
        db.commit()
        db.refresh(row_b)
        result = _blog_row_to_seo(row_b)

    gsc_note = "Indexing request recorded. Connect Google Search Console in Site Settings to submit to Google."
    if settings.gsc_connected and _decrypt(settings.gsc_refresh_token_encrypted):
        # Placeholder for full OAuth URL Inspection — record intent when connected
        gsc_note = (
            "Indexing request timestamp stored. Google Search Console URL Inspection "
            f"should be used for {url} (full OAuth inspection requires GSC API scopes)."
        )
    result["request_note"] = gsc_note
    return result


def list_redirects(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(select(SiteSeoRedirect).order_by(SiteSeoRedirect.updated_at.desc())).scalars().all()
    return [
        {
            "id": r.id,
            "from_path": r.from_path,
            "to_path": r.to_path,
            "status_code": r.status_code,
            "source": r.source,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def create_redirect(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    row = upsert_redirect(
        db,
        str(payload.get("from_path") or ""),
        str(payload.get("to_path") or ""),
        status_code=int(payload.get("status_code") or 301),
        source="manual",
    )
    return {
        "id": row.id,
        "from_path": row.from_path,
        "to_path": row.to_path,
        "status_code": row.status_code,
        "source": row.source,
    }


def delete_redirect(db: Session, redirect_id: str) -> None:
    row = db.execute(select(SiteSeoRedirect).where(SiteSeoRedirect.id == redirect_id)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Redirect not found")
    db.delete(row)
    db.commit()


def resolve_redirect(db: Session, path: str) -> dict[str, Any] | None:
    frm = _normalize_path(path)
    row = db.execute(select(SiteSeoRedirect).where(SiteSeoRedirect.from_path == frm)).scalar_one_or_none()
    if not row:
        return None
    return {"from_path": row.from_path, "to_path": row.to_path, "status_code": row.status_code}


def _is_indexable_robots(robots: str) -> bool:
    return "noindex" not in (robots or "").lower()


def build_sitemap_entries(db: Session) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = [{"path": p, "changefreq": "weekly", "priority": "0.8"} for p in STATIC_SITEMAP_PATHS]
    for row in db.execute(select(SiteBlogNewsItem).where(SiteBlogNewsItem.is_visible.is_(True))).scalars().all():
        if not _is_indexable_robots(row.robots):
            continue
        entries.append(
            {
                "path": f"{PATH_PREFIX[row.kind]}{row.slug}",
                "changefreq": "monthly",
                "priority": "0.6",
                "lastmod": row.published_at.isoformat() if row.published_at else "",
            }
        )
    for row in db.execute(select(FAQItem).where(FAQItem.is_published.is_(True))).scalars().all():
        if not row.slug or not _is_indexable_robots(row.robots):
            continue
        entries.append(
            {
                "path": f"/faq/{row.slug}",
                "changefreq": "monthly",
                "priority": "0.55",
                "lastmod": (row.seo_updated_at or row.updated_at or row.created_at).date().isoformat()
                if (row.seo_updated_at or row.updated_at or row.created_at)
                else "",
            }
        )
    return entries


def regenerate_sitemap(db: Session) -> dict[str, Any]:
    settings = ensure_settings(db)
    entries = build_sitemap_entries(db)
    settings.sitemap_last_generated_at = datetime.utcnow()
    settings.updated_at = datetime.utcnow()
    db.commit()
    news_eligible = 0
    if settings.google_news_enabled:
        cutoff = datetime.utcnow() - timedelta(days=2)
        for row in db.execute(select(SiteBlogNewsItem).where(SiteBlogNewsItem.kind == KIND_NEWS)).scalars().all():
            if not row.is_visible or not _is_indexable_robots(row.robots):
                continue
            pub = datetime.combine(row.published_at, datetime.min.time()) if row.published_at else None
            if pub and pub >= cutoff:
                news_eligible += 1
    return {
        "count": len(entries),
        "entries": entries,
        "last_generated_at": settings.sitemap_last_generated_at.isoformat(),
        "news_eligible_count": news_eligible,
        "sitemap_url": f"{SITE_ORIGIN}/sitemap.xml",
        "news_sitemap_url": f"{SITE_ORIGIN}/news-sitemap.xml",
    }


def sitemap_stats(db: Session) -> dict[str, Any]:
    settings = ensure_settings(db)
    entries = build_sitemap_entries(db)
    news_eligible = 0
    if settings.google_news_enabled:
        cutoff = datetime.utcnow() - timedelta(days=2)
        for row in db.execute(select(SiteBlogNewsItem).where(SiteBlogNewsItem.kind == KIND_NEWS)).scalars().all():
            if not row.is_visible or not _is_indexable_robots(row.robots):
                continue
            pub = datetime.combine(row.published_at, datetime.min.time()) if row.published_at else None
            if pub and pub >= cutoff:
                news_eligible += 1
    return {
        "count": len(entries),
        "last_generated_at": settings.sitemap_last_generated_at.isoformat() if settings.sitemap_last_generated_at else None,
        "last_submitted_at": settings.sitemap_last_submitted_at.isoformat() if settings.sitemap_last_submitted_at else None,
        "news_eligible_count": news_eligible,
        "google_news_enabled": bool(settings.google_news_enabled),
        "sitemap_url": f"{SITE_ORIGIN}/sitemap.xml",
        "news_sitemap_url": f"{SITE_ORIGIN}/news-sitemap.xml",
        "indexnow_key": settings.indexnow_key or "",
        "indexnow_last_pinged_at": settings.indexnow_last_pinged_at.isoformat() if settings.indexnow_last_pinged_at else None,
    }


def generate_indexnow_key(db: Session) -> dict[str, Any]:
    settings = ensure_settings(db)
    key = secrets.token_hex(16)
    settings.indexnow_key = key
    settings.updated_at = datetime.utcnow()
    db.commit()
    return {
        "indexnow_key": key,
        "verification_url": f"{SITE_ORIGIN}/{key}.txt",
        "note": "Key file is served dynamically at /{key}.txt on the public site.",
    }


def notify_indexnow(db: Session) -> dict[str, Any]:
    settings = ensure_settings(db)
    key = (settings.indexnow_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="Generate an IndexNow key first.")
    since = settings.indexnow_last_pinged_at or (datetime.utcnow() - timedelta(days=7))
    urls: list[str] = []
    for row in db.execute(select(SiteBlogNewsItem).where(SiteBlogNewsItem.is_visible.is_(True))).scalars().all():
        if not _is_indexable_robots(row.robots):
            continue
        ts = row.seo_updated_at or row.updated_at
        if ts and ts >= since:
            urls.append(f"{SITE_ORIGIN}{PATH_PREFIX[row.kind]}{row.slug}")
    for row in db.execute(select(FAQItem).where(FAQItem.is_published.is_(True))).scalars().all():
        if not row.slug or not _is_indexable_robots(row.robots):
            continue
        ts = row.seo_updated_at or row.updated_at
        if ts and ts >= since:
            urls.append(f"{SITE_ORIGIN}/faq/{row.slug}")
    urls = urls[:10000] or [f"{SITE_ORIGIN}/"]
    payload = {
        "host": "voxbulk.com",
        "key": key,
        "keyLocation": f"{SITE_ORIGIN}/{key}.txt",
        "urlList": urls,
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            res = client.post("https://api.indexnow.org/indexnow", json=payload)
            ok = res.status_code in {200, 202}
            detail = res.text[:500]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"IndexNow request failed: {exc}") from exc
    settings.indexnow_last_pinged_at = datetime.utcnow()
    settings.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": ok, "url_count": len(urls), "status_code": res.status_code, "detail": detail}


def connect_psi(db: Session, api_key: str) -> dict[str, Any]:
    key = (api_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="PageSpeed API key required")
    url = (
        "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
        f"?url={quote(SITE_ORIGIN + '/', safe='')}&key={quote(key)}&strategy=mobile"
    )
    try:
        with httpx.Client(timeout=60.0) as client:
            res = client.get(url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"PageSpeed request failed: {exc}") from exc
    if res.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"PageSpeed key invalid or quota error ({res.status_code})")
    settings = ensure_settings(db)
    settings.psi_api_key_encrypted = _encrypt(key)
    settings.psi_connected = True
    settings.updated_at = datetime.utcnow()
    db.commit()
    return {"connected": True}


def connect_moz(db: Session, access_id: str, secret_key: str) -> dict[str, Any]:
    aid = (access_id or "").strip()
    secret = (secret_key or "").strip()
    if not aid or not secret:
        raise HTTPException(status_code=400, detail="Moz Access ID and Secret Key required")
    expires = int(time.time() + 300)
    string_to_sign = f"{aid}\n{expires}".encode()
    sig = base64.b64encode(hmac.new(secret.encode(), string_to_sign, hashlib.sha1).digest()).decode()
    url = f"https://lsapi.seomoz.com/v2/url_metrics"
    try:
        with httpx.Client(timeout=30.0) as client:
            res = client.post(
                url,
                auth=(aid, secret),
                json={"targets": ["voxbulk.com"]},
            )
            if res.status_code >= 400:
                # try legacy signed style
                res = client.get(
                    f"https://lsapi.seomoz.com/linkscape/url-metrics/voxbulk.com?Cols=103079215108&AccessID={quote(aid)}&Expires={expires}&Signature={quote(sig)}"
                )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Moz request failed: {exc}") from exc
    if res.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Moz credentials rejected ({res.status_code})")
    settings = ensure_settings(db)
    prev = settings.moz_domain_authority
    da = None
    try:
        data = res.json()
        if isinstance(data, dict):
            results = data.get("results") or data.get("result") or []
            if isinstance(results, list) and results:
                da = results[0].get("domain_authority") or results[0].get("pda")
            da = da or data.get("domain_authority") or data.get("pda")
        if isinstance(data, list) and data:
            da = data[0].get("pda") or data[0].get("domain_authority")
    except Exception:
        da = None
    settings.moz_access_id_encrypted = _encrypt(aid)
    settings.moz_secret_key_encrypted = _encrypt(secret)
    settings.moz_connected = True
    if da is not None:
        settings.moz_domain_authority_prev = prev
        settings.moz_domain_authority = str(da)
    settings.updated_at = datetime.utcnow()
    db.commit()
    return {"connected": True, "domain_authority": settings.moz_domain_authority}


def run_psi_check(db: Session) -> dict[str, Any]:
    settings = ensure_settings(db)
    key = _decrypt(settings.psi_api_key_encrypted)
    if not key or not settings.psi_connected:
        raise HTTPException(status_code=400, detail="Connect a PageSpeed Insights API key in Site Settings first.")
    url = (
        "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
        f"?url={quote(SITE_ORIGIN + '/', safe='')}&key={quote(key)}&strategy=mobile&category=performance"
    )
    with httpx.Client(timeout=90.0) as client:
        res = client.get(url)
    if res.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"PageSpeed failed ({res.status_code})")
    data = res.json()
    audits = (data.get("lighthouseResult") or {}).get("audits") or {}
    cats = (data.get("lighthouseResult") or {}).get("categories") or {}
    perf = (cats.get("performance") or {}).get("score")
    lcp = (audits.get("largest-contentful-paint") or {}).get("numericValue")
    cls = (audits.get("cumulative-layout-shift") or {}).get("numericValue")
    inp = (audits.get("interaction-to-next-paint") or {}).get("numericValue") or (
        audits.get("total-blocking-time") or {}
    ).get("numericValue")
    snap = ensure_health(db)
    snap.lcp_ms = str(int(lcp)) if lcp is not None else snap.lcp_ms
    snap.cls = f"{cls:.3f}" if cls is not None else snap.cls
    snap.inp_ms = str(int(inp)) if inp is not None else snap.inp_ms
    snap.psi_score = str(int(perf * 100)) if perf is not None else snap.psi_score
    snap.mobile_note = "Mobile performance from PageSpeed Insights (mobile strategy)."
    snap.checked_at = datetime.utcnow()
    snap.site_health_score = _compute_health_score(snap)
    snap.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(snap)
    return health_to_dict(snap)


def _compute_health_score(snap: SiteSeoHealthSnapshot) -> int:
    score = 70
    try:
        if snap.psi_score:
            score = int(float(snap.psi_score))
    except ValueError:
        pass
    try:
        broken = json.loads(snap.broken_links_json or "[]")
        score = max(0, score - min(40, len(broken) * 5))
    except Exception:
        pass
    return max(0, min(100, score))


def health_to_dict(snap: SiteSeoHealthSnapshot) -> dict[str, Any]:
    try:
        broken = json.loads(snap.broken_links_json or "[]")
    except Exception:
        broken = []
    try:
        structured = json.loads(snap.structured_data_json or "{}")
    except Exception:
        structured = {}
    return {
        "site_health_score": snap.site_health_score,
        "lcp_ms": snap.lcp_ms,
        "inp_ms": snap.inp_ms,
        "cls": snap.cls,
        "psi_score": snap.psi_score,
        "mobile_note": snap.mobile_note,
        "broken_links": broken,
        "structured_data": structured,
        "checked_at": snap.checked_at.isoformat() if snap.checked_at else None,
    }


def scan_broken_links(db: Session) -> dict[str, Any]:
    entries = build_sitemap_entries(db)
    broken: list[dict[str, str]] = []
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        for ent in entries[:80]:
            path = ent["path"]
            url = f"{SITE_ORIGIN}{path}"
            try:
                res = client.head(url)
                if res.status_code == 405:
                    res = client.get(url)
                if res.status_code >= 400:
                    broken.append({"url": url, "status": str(res.status_code), "source": "sitemap"})
            except Exception as exc:
                broken.append({"url": url, "status": "error", "source": str(exc)[:80]})
    snap = ensure_health(db)
    snap.broken_links_json = json.dumps(broken)
    # lightweight structured data summary
    blog_n = len([e for e in entries if e["path"].startswith("/blog/")])
    news_n = len([e for e in entries if e["path"].startswith("/news/")])
    faq_n = len([e for e in entries if e["path"].startswith("/faq/")])
    snap.structured_data_json = json.dumps(
        {
            "article": {"ok": blog_n > 0, "count": blog_n},
            "news_article": {"ok": news_n > 0, "count": news_n},
            "faq_page": {"ok": faq_n > 0, "count": faq_n},
        }
    )
    snap.checked_at = datetime.utcnow()
    snap.site_health_score = _compute_health_score(snap)
    snap.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(snap)
    return health_to_dict(snap)


def mark_broken_fixed(db: Session, url: str) -> dict[str, Any]:
    snap = ensure_health(db)
    try:
        broken = json.loads(snap.broken_links_json or "[]")
    except Exception:
        broken = []
    target = (url or "").strip()
    # re-check
    ok = False
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            res = client.head(target)
            if res.status_code == 405:
                res = client.get(target)
            ok = res.status_code < 400
    except Exception:
        ok = False
    if not ok:
        raise HTTPException(status_code=400, detail="URL still returns an error; not removed.")
    broken = [b for b in broken if b.get("url") != target]
    snap.broken_links_json = json.dumps(broken)
    snap.site_health_score = _compute_health_score(snap)
    snap.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(snap)
    return health_to_dict(snap)


def submit_sitemap_to_google(db: Session) -> dict[str, Any]:
    settings = ensure_settings(db)
    settings.sitemap_last_submitted_at = datetime.utcnow()
    settings.updated_at = datetime.utcnow()
    db.commit()
    if not settings.gsc_connected:
        return {
            "ok": False,
            "submitted_at": settings.sitemap_last_submitted_at.isoformat(),
            "note": "Timestamp saved. Connect Google Search Console in Site Settings to submit via API.",
        }
    return {
        "ok": True,
        "submitted_at": settings.sitemap_last_submitted_at.isoformat(),
        "note": "Submission timestamp recorded. Full GSC Sitemaps API submit requires OAuth scopes.",
    }


def public_faq_list(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.execute(
            select(FAQItem)
            .where(FAQItem.is_published.is_(True))
            .order_by(FAQItem.sort_order.asc(), FAQItem.id.desc())
        )
        .scalars()
        .all()
    )
    out = []
    for r in rows:
        if not r.slug:
            continue
        if "noindex" in (r.robots or "").lower():
            # still listable? For public FAQ index, skip noindex pages
            continue
        out.append(_faq_row_to_seo(r))
    return out


def public_faq_by_slug(db: Session, slug: str) -> dict[str, Any]:
    row = db.execute(select(FAQItem).where(FAQItem.slug == slug, FAQItem.is_published.is_(True))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="FAQ not found")
    return _faq_row_to_seo(row)


def public_content_seo(db: Session, kind: str, slug: str) -> dict[str, Any]:
    k = kind.strip().lower()
    if k == KIND_FAQ:
        return public_faq_by_slug(db, slug)
    row = db.execute(
        select(SiteBlogNewsItem).where(
            SiteBlogNewsItem.kind == k,
            SiteBlogNewsItem.slug == slug,
            SiteBlogNewsItem.is_visible.is_(True),
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return _blog_row_to_seo(row)
