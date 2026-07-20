"""Submit sitemaps to Google / Bing / Yandex and manage SEO keyword ideas."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.faq import FAQItem
from app.models.site_blog_news_item import SiteBlogNewsItem
from app.models.site_seo import SiteSeoSettings
from app.services import site_seo_service as seo

SITE_ORIGIN = seo.SITE_ORIGIN
SITEMAP_URL = f"{SITE_ORIGIN}/sitemap.xml"
NEWS_SITEMAP_URL = f"{SITE_ORIGIN}/news-sitemap.xml"

_KEYWORD_SUFFIXES = (
    "software",
    "platform",
    "tool",
    "UK",
    "for business",
    "pricing",
    "vs email",
    "automation",
)
_KEYWORD_PREFIXES = ("best ", "ai ", "whatsapp ")


def _loads_json(raw: str | None, fallback: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return fallback


def _dump_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def engine_status(db: Session) -> dict[str, Any]:
    row = seo.ensure_settings(db)
    last = _loads_json(getattr(row, "engines_last_result_json", None), {})
    if not isinstance(last, dict):
        last = {}
    return {
        "auto_submit_weekly": bool(getattr(row, "auto_submit_weekly", False)),
        "auto_indexnow_on_publish": bool(getattr(row, "auto_indexnow_on_publish", True)),
        "engines_last_run_at": row.engines_last_run_at.isoformat() if row.engines_last_run_at else None,
        "engines_last_result": last,
        "google": {
            "connected": bool(row.gsc_connected),
            "property_url": row.gsc_property_url or "",
            "last_submitted_at": row.sitemap_last_submitted_at.isoformat() if row.sitemap_last_submitted_at else None,
            "last_error": getattr(row, "google_last_submit_error", "") or "",
        },
        "bing": {
            "connected": bool(getattr(row, "bing_connected", False)),
            "api_key_set": bool(seo._decrypt(getattr(row, "bing_api_key_encrypted", None))),
            "site_url": getattr(row, "bing_site_url", None) or SITE_ORIGIN,
            "last_submitted_at": row.bing_last_submitted_at.isoformat()
            if getattr(row, "bing_last_submitted_at", None)
            else None,
            "last_error": getattr(row, "bing_last_error", "") or "",
        },
        "yandex": {
            "connected": bool(getattr(row, "yandex_connected", False)),
            "token_set": bool(seo._decrypt(getattr(row, "yandex_oauth_token_encrypted", None))),
            "user_id": getattr(row, "yandex_user_id", "") or "",
            "host_id": getattr(row, "yandex_host_id", "") or "",
            "last_submitted_at": row.yandex_last_submitted_at.isoformat()
            if getattr(row, "yandex_last_submitted_at", None)
            else None,
            "last_error": getattr(row, "yandex_last_error", "") or "",
        },
        "indexnow": {
            "key_set": bool(row.indexnow_key),
            "last_pinged_at": row.indexnow_last_pinged_at.isoformat() if row.indexnow_last_pinged_at else None,
        },
        "sitemap_url": SITEMAP_URL,
        "news_sitemap_url": NEWS_SITEMAP_URL,
    }


def connect_bing(db: Session, api_key: str, site_url: str | None = None) -> dict[str, Any]:
    key = (api_key or "").strip()
    if len(key) < 8:
        raise HTTPException(status_code=400, detail="Bing Webmaster API key required")
    site = (site_url or SITE_ORIGIN).strip().rstrip("/") or SITE_ORIGIN
    if not site.startswith("http"):
        site = f"https://{site}"
    # Validate key by listing feeds (or sites)
    url = f"https://ssl.bing.com/webmaster/api.svc/json/GetUserSites?apikey={quote(key, safe='')}"
    try:
        with httpx.Client(timeout=30.0) as client:
            res = client.get(url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Bing API request failed: {exc}") from exc
    if res.status_code >= 400:
        raise HTTPException(
            status_code=400,
            detail=f"Bing API key invalid or not authorised ({res.status_code}): {res.text[:240]}",
        )
    row = seo.ensure_settings(db)
    row.bing_api_key_encrypted = seo._encrypt(key)
    row.bing_site_url = site
    row.bing_connected = True
    row.bing_last_error = ""
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"connected": True, "site_url": site}


def disconnect_bing(db: Session) -> dict[str, Any]:
    row = seo.ensure_settings(db)
    row.bing_api_key_encrypted = None
    row.bing_connected = False
    row.bing_last_error = ""
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"connected": False}


def connect_yandex(db: Session, oauth_token: str) -> dict[str, Any]:
    token = (oauth_token or "").strip()
    if len(token) < 8:
        raise HTTPException(status_code=400, detail="Yandex Webmaster OAuth token required")
    headers = {"Authorization": f"OAuth {token}"}
    try:
        with httpx.Client(timeout=30.0) as client:
            user_res = client.get("https://api.webmaster.yandex.net/v4/user", headers=headers)
            if user_res.status_code >= 400:
                raise HTTPException(
                    status_code=400,
                    detail=f"Yandex token invalid ({user_res.status_code}): {user_res.text[:240]}",
                )
            user_id = str((user_res.json() or {}).get("user_id") or "").strip()
            if not user_id:
                raise HTTPException(status_code=400, detail="Yandex did not return a user_id")
            hosts_res = client.get(
                f"https://api.webmaster.yandex.net/v4/user/{user_id}/hosts",
                headers=headers,
            )
            if hosts_res.status_code >= 400:
                raise HTTPException(
                    status_code=400,
                    detail=f"Could not list Yandex hosts ({hosts_res.status_code}): {hosts_res.text[:240]}",
                )
            hosts = (hosts_res.json() or {}).get("hosts") or []
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Yandex API request failed: {exc}") from exc

    host_id = ""
    for h in hosts:
        ascii_host = str(h.get("ascii_host_url") or h.get("host_url") or "").lower()
        hid = str(h.get("host_id") or "").strip()
        if "voxbulk.com" in ascii_host and hid:
            host_id = hid
            break
    if not host_id and hosts:
        host_id = str(hosts[0].get("host_id") or "").strip()
    if not host_id:
        raise HTTPException(
            status_code=400,
            detail="No Yandex Webmaster host found. Add https://voxbulk.com in Yandex Webmaster first.",
        )

    row = seo.ensure_settings(db)
    row.yandex_oauth_token_encrypted = seo._encrypt(token)
    row.yandex_user_id = user_id
    row.yandex_host_id = host_id
    row.yandex_connected = True
    row.yandex_last_error = ""
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"connected": True, "user_id": user_id, "host_id": host_id}


def disconnect_yandex(db: Session) -> dict[str, Any]:
    row = seo.ensure_settings(db)
    row.yandex_oauth_token_encrypted = None
    row.yandex_user_id = ""
    row.yandex_host_id = ""
    row.yandex_connected = False
    row.yandex_last_error = ""
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"connected": False}


def submit_sitemap_google(db: Session) -> dict[str, Any]:
    from app.services.gsc_oauth_service import submit_sitemap as gsc_submit_sitemap

    row = seo.ensure_settings(db)
    now = datetime.utcnow()
    try:
        result = gsc_submit_sitemap(db, SITEMAP_URL)
        row.sitemap_last_submitted_at = now
        row.google_last_submit_error = ""
        row.updated_at = now
        db.commit()
        return {"ok": True, "engine": "google", "submitted_at": now.isoformat(), **result}
    except HTTPException as exc:
        row.google_last_submit_error = str(exc.detail or "")[:500]
        row.updated_at = now
        db.commit()
        return {"ok": False, "engine": "google", "error": str(exc.detail or "")[:500]}
    except Exception as exc:
        row.google_last_submit_error = str(exc)[:500]
        row.updated_at = now
        db.commit()
        return {"ok": False, "engine": "google", "error": str(exc)[:500]}


def submit_sitemap_bing(db: Session) -> dict[str, Any]:
    row = seo.ensure_settings(db)
    key = seo._decrypt(getattr(row, "bing_api_key_encrypted", None))
    if not row.bing_connected or not key:
        return {"ok": False, "engine": "bing", "error": "Connect Bing Webmaster API key first."}
    site = (row.bing_site_url or SITE_ORIGIN).rstrip("/")
    url = f"https://ssl.bing.com/webmaster/api.svc/json/SubmitFeed?apikey={quote(key, safe='')}"
    now = datetime.utcnow()
    try:
        with httpx.Client(timeout=30.0) as client:
            res = client.post(
                url,
                headers={"Content-Type": "application/json; charset=utf-8"},
                json={"siteUrl": site, "feedUrl": SITEMAP_URL},
            )
        ok = res.status_code < 400
        detail = (res.text or "")[:400]
        row.bing_last_submitted_at = now if ok else row.bing_last_submitted_at
        row.bing_last_error = "" if ok else detail
        row.updated_at = now
        db.commit()
        return {
            "ok": ok,
            "engine": "bing",
            "status_code": res.status_code,
            "submitted_at": now.isoformat() if ok else None,
            "detail": detail,
        }
    except Exception as exc:
        row.bing_last_error = str(exc)[:500]
        row.updated_at = now
        db.commit()
        return {"ok": False, "engine": "bing", "error": str(exc)[:500]}


def submit_sitemap_yandex(db: Session) -> dict[str, Any]:
    row = seo.ensure_settings(db)
    token = seo._decrypt(getattr(row, "yandex_oauth_token_encrypted", None))
    user_id = (row.yandex_user_id or "").strip()
    host_id = (row.yandex_host_id or "").strip()
    if not row.yandex_connected or not token or not user_id or not host_id:
        return {"ok": False, "engine": "yandex", "error": "Connect Yandex Webmaster token first."}
    api = f"https://api.webmaster.yandex.net/v4/user/{user_id}/hosts/{host_id}/user-added-sitemaps"
    now = datetime.utcnow()
    try:
        with httpx.Client(timeout=30.0) as client:
            res = client.post(
                api,
                headers={"Authorization": f"OAuth {token}", "Content-Type": "application/json"},
                json={"url": SITEMAP_URL},
            )
        # 202/201/200 or 409 already added = success for our purposes
        ok = res.status_code < 400 or res.status_code == 409
        detail = (res.text or "")[:400]
        if ok:
            row.yandex_last_submitted_at = now
            row.yandex_last_error = ""
        else:
            row.yandex_last_error = detail
        row.updated_at = now
        db.commit()
        return {
            "ok": ok,
            "engine": "yandex",
            "status_code": res.status_code,
            "submitted_at": now.isoformat() if ok else None,
            "detail": detail,
        }
    except Exception as exc:
        row.yandex_last_error = str(exc)[:500]
        row.updated_at = now
        db.commit()
        return {"ok": False, "engine": "yandex", "error": str(exc)[:500]}


def run_engine_submit(db: Session, *, source: str = "manual") -> dict[str, Any]:
    """Regenerate sitemap timestamp, IndexNow ping, then submit to connected engines."""
    seo.regenerate_sitemap(db)
    indexnow: dict[str, Any] = {"ok": False, "skipped": True}
    try:
        if seo.ensure_settings(db).indexnow_key:
            indexnow = seo.notify_indexnow(db)
            indexnow["skipped"] = False
    except Exception as exc:
        indexnow = {"ok": False, "error": str(exc)[:300], "skipped": False}

    results = {
        "source": source,
        "ran_at": datetime.utcnow().isoformat(),
        "indexnow": indexnow,
        "google": submit_sitemap_google(db),
        "bing": submit_sitemap_bing(db),
        "yandex": submit_sitemap_yandex(db),
    }
    row = seo.ensure_settings(db)
    row.engines_last_run_at = datetime.utcnow()
    row.engines_last_result_json = _dump_json(results)
    row.updated_at = datetime.utcnow()
    db.commit()
    return results


def weekly_auto_submit_if_enabled(db: Session) -> dict[str, Any]:
    row = seo.ensure_settings(db)
    if not getattr(row, "auto_submit_weekly", False):
        return {"ok": True, "skipped": True, "reason": "auto_submit_weekly is off"}
    return run_engine_submit(db, source="weekly_celery")


def _normalize_phrase(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip().lower())


def _seed_phrases(db: Session) -> list[str]:
    row = seo.ensure_settings(db)
    seeds: list[str] = []
    for part in (
        row.home_focus_keyword,
        row.home_tags,
        getattr(row, "default_meta_description", "") or "",
    ):
        seeds.extend(re.split(r"[,|;]", part or ""))
    pages = seo._loads_marketing_pages(getattr(row, "marketing_pages_json", None))
    for page in pages.values():
        seeds.append(str(page.get("keywords") or ""))
        seeds.append(str(page.get("title") or ""))
    for blog in db.execute(select(SiteBlogNewsItem).where(SiteBlogNewsItem.is_visible.is_(True))).scalars().all():
        seeds.append(blog.focus_keyword or "")
        seeds.append(blog.tags or "")
        seeds.append(blog.title or "")
    for faq in db.execute(select(FAQItem).where(FAQItem.is_published.is_(True))).scalars().all():
        seeds.append(faq.focus_keyword or "")
        seeds.append(faq.tags or "")
        seeds.append(faq.question or "")
    out: list[str] = []
    seen: set[str] = set()
    for s in seeds:
        for chunk in re.split(r"[,|;]", s or ""):
            p = _normalize_phrase(chunk)
            if len(p) < 3 or len(p) > 80:
                continue
            if p in seen:
                continue
            # skip whole sentences
            if p.count(" ") > 8:
                continue
            seen.add(p)
            out.append(p)
    return out[:80]


def refresh_keyword_ideas(db: Session) -> dict[str, Any]:
    row = seo.ensure_settings(db)
    existing = _loads_json(getattr(row, "keyword_ideas_json", None), [])
    if not isinstance(existing, list):
        existing = []
    kept = [i for i in existing if isinstance(i, dict) and i.get("status") in {"accepted", "dismissed"}]
    kept_phrases = {_normalize_phrase(str(i.get("phrase") or "")) for i in kept}
    seeds = _seed_phrases(db)
    ideas: list[dict[str, Any]] = []
    for seed in seeds[:25]:
        candidates = [seed]
        for pref in _KEYWORD_PREFIXES:
            candidates.append(f"{pref}{seed}".strip())
        for suf in _KEYWORD_SUFFIXES:
            candidates.append(f"{seed} {suf}".strip())
        for phrase in candidates:
            n = _normalize_phrase(phrase)
            if n in kept_phrases or any(_normalize_phrase(i.get("phrase", "")) == n for i in ideas):
                continue
            if len(n) < 4:
                continue
            target = "home"
            if "survey" in n or "whatsapp" in n:
                target = "surveys"
            elif "feedback" in n or "qr" in n:
                target = "feedback"
            elif "interview" in n or "recruit" in n or "hiring" in n:
                target = "recruitment"
            elif "price" in n or "pricing" in n or "cost" in n:
                target = "pricing"
            ideas.append(
                {
                    "id": str(uuid.uuid4()),
                    "phrase": phrase[:120],
                    "source": "seed_expand",
                    "status": "suggested",
                    "target": target,
                    "created_at": datetime.utcnow().isoformat(),
                }
            )
            if len(ideas) >= 40:
                break
        if len(ideas) >= 40:
            break
    merged = kept + ideas
    row.keyword_ideas_json = _dump_json(merged)
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"items": merged, "suggested_count": len(ideas)}


def list_keyword_ideas(db: Session) -> dict[str, Any]:
    row = seo.ensure_settings(db)
    items = _loads_json(getattr(row, "keyword_ideas_json", None), [])
    if not isinstance(items, list) or not items:
        return refresh_keyword_ideas(db)
    return {"items": items, "suggested_count": sum(1 for i in items if i.get("status") == "suggested")}


def _apply_keyword_to_target(db: Session, phrase: str, target: str) -> None:
    row = seo.ensure_settings(db)
    t = (target or "home").strip().lower()
    phrase = phrase.strip()
    if t == "home":
        tags = [x.strip() for x in (row.home_tags or "").split(",") if x.strip()]
        if phrase.lower() not in {x.lower() for x in tags}:
            tags.append(phrase)
            row.home_tags = ", ".join(tags)[:500]
        if not (row.home_focus_keyword or "").strip():
            row.home_focus_keyword = phrase[:200]
        return
    if t in seo.MARKETING_PAGE_KEYS:
        pages = seo._loads_marketing_pages(getattr(row, "marketing_pages_json", None))
        page = pages.get(t) or {}
        kws = [x.strip() for x in str(page.get("keywords") or "").split(",") if x.strip()]
        if phrase.lower() not in {x.lower() for x in kws}:
            kws.append(phrase)
            page["keywords"] = ", ".join(kws)[:500]
            pages[t] = page
            row.marketing_pages_json = seo._dump_marketing_pages(pages)


def accept_keyword_idea(db: Session, idea_id: str, target: str | None = None) -> dict[str, Any]:
    row = seo.ensure_settings(db)
    items = _loads_json(getattr(row, "keyword_ideas_json", None), [])
    if not isinstance(items, list):
        items = []
    found = None
    for item in items:
        if str(item.get("id")) == str(idea_id):
            found = item
            break
    if not found:
        raise HTTPException(status_code=404, detail="Keyword idea not found")
    dest = (target or found.get("target") or "home").strip().lower()
    phrase = str(found.get("phrase") or "").strip()
    if not phrase:
        raise HTTPException(status_code=400, detail="Empty keyword phrase")
    _apply_keyword_to_target(db, phrase, dest)
    found["status"] = "accepted"
    found["target"] = dest
    found["accepted_at"] = datetime.utcnow().isoformat()
    row.keyword_ideas_json = _dump_json(items)
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"item": found, "note": f"Added “{phrase}” to {dest} keywords. No new page was published."}


def dismiss_keyword_idea(db: Session, idea_id: str) -> dict[str, Any]:
    row = seo.ensure_settings(db)
    items = _loads_json(getattr(row, "keyword_ideas_json", None), [])
    if not isinstance(items, list):
        items = []
    found = None
    for item in items:
        if str(item.get("id")) == str(idea_id):
            found = item
            break
    if not found:
        raise HTTPException(status_code=404, detail="Keyword idea not found")
    found["status"] = "dismissed"
    found["dismissed_at"] = datetime.utcnow().isoformat()
    row.keyword_ideas_json = _dump_json(items)
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"item": found}
