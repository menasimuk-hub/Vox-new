"""Built-in expo exhibitor directory scraper (Easyfairs + generic HTML fallback).

Finds exhibitor/stand pages from a directory URL, pulls contact emails from
stand descriptions and company websites — no Apify actor required.
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlencode, urljoin, urlparse

import httpx

ProgressCallback = Callable[[dict[str, Any]], None]

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EASYFAIRS_LOADER = "https://my.easyfairs.com/widgets/api/loader/?hostDomain={host}&ver=1.0.8"
EASYFAIRS_STANDS_SEARCH = "https://my.easyfairs.com/widgets/api/stands/?language=en"
EASYFAIRS_STAND_DETAIL = "https://my.easyfairs.com/widgets/api/stands/{stand_id}/?language=en&edition={edition}"

_JUNK_EMAIL_SUBSTR = (
    "example.com",
    "sentry.",
    "wixpress",
    "easyfairs",
    "cloudflare",
    "noreply@",
    "no-reply@",
    "donotreply@",
    "asp.events",
    "reedexpo",
    "rxweb",
    "closerstill",
    "ukimediaevents",
    "webpack",
    "schema.org",
)


class ExpoDirectoryScraperError(ValueError):
    pass


class ScrapeAborted(Exception):
    """Raised when admin force-pauses / aborts a running directory scrape."""


class ExpoDirectoryScraper:
    @staticmethod
    def _headers(directory_url: str) -> dict[str, str]:
        parsed = urlparse(directory_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        return {
            "User-Agent": (
                "Mozilla/5.0 (compatible; VoxBulkExpoScraper/1.0; +https://voxbulk.com)"
            ),
            "Accept": "application/json,text/html,*/*",
            "Origin": origin,
            "Referer": directory_url if directory_url.endswith("/") else directory_url + "/",
        }

    @staticmethod
    def _host(directory_url: str) -> str:
        host = (urlparse(directory_url).netloc or "").lower().strip()
        if host.startswith("www."):
            # Easyfairs loader expects the public host as used on the site
            pass
        if not host:
            raise ExpoDirectoryScraperError("Invalid directory URL")
        return host

    @staticmethod
    def _slugify(name: str) -> str:
        s = str(name or "").lower().strip()
        s = re.sub(r"[^a-z0-9]+", "-", s)
        return s.strip("-") or "exhibitor"

    @staticmethod
    def clean_emails(text: str) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()
        for raw in EMAIL_RE.findall(text or ""):
            email = raw.strip().lower().rstrip(".")
            # Fix common double-dot typos from OCR/CMS (sales@allpack..uk.com)
            email = re.sub(r"\.{2,}", ".", email)
            if "@" not in email:
                continue
            local, _, domain = email.partition("@")
            if not local or not domain or "." not in domain:
                continue
            if any(j in email for j in _JUNK_EMAIL_SUBSTR):
                continue
            if email.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")):
                continue
            if email in seen:
                continue
            seen.add(email)
            found.append(email)
        return found

    @staticmethod
    def detect_easyfairs_editions(directory_url: str) -> list[int]:
        host = ExpoDirectoryScraper._host(directory_url)
        url = EASYFAIRS_LOADER.format(host=host)
        try:
            with httpx.Client(timeout=45.0, follow_redirects=True) as client:
                resp = client.get(url, headers=ExpoDirectoryScraper._headers(directory_url))
                if resp.status_code >= 400:
                    return []
                text = resp.text or ""
        except Exception:
            return []
        m = re.search(r"activeEditions\s*=\s*\[([0-9,\s]+)\]", text)
        if not m:
            return []
        return [int(x) for x in re.findall(r"\d+", m.group(1))]

    @staticmethod
    def _search_stands(directory_url: str, editions: list[int]) -> list[dict[str, Any]]:
        if not editions:
            raise ExpoDirectoryScraperError("No Easyfairs editions found for this site")
        filt = " OR ".join(f"containerId: {e}" for e in editions)
        headers = {
            **ExpoDirectoryScraper._headers(directory_url),
            "Content-Type": "application/json",
            "Accept": "*/*",
        }
        hits: list[dict[str, Any]] = []
        page = 0
        nb_pages = 1
        with httpx.Client(timeout=90.0, follow_redirects=True) as client:
            while page < nb_pages and page < 50:
                body = [
                    {
                        "indexName": "stands",
                        "params": {
                            "query": "",
                            "hitsPerPage": 100,
                            "page": page,
                            "filters": filt,
                        },
                    }
                ]
                resp = client.post(EASYFAIRS_STANDS_SEARCH, headers=headers, json=body)
                if resp.status_code >= 400:
                    raise ExpoDirectoryScraperError(
                        f"Easyfairs stands search failed ({resp.status_code}): {resp.text[:300]}"
                    )
                data = resp.json() or {}
                results = data.get("results") or []
                if not results:
                    break
                res = results[0] if isinstance(results[0], dict) else {}
                batch = [h for h in (res.get("hits") or []) if isinstance(h, dict)]
                hits.extend(batch)
                nb_pages = max(1, int(res.get("nbPages") or 1))
                page += 1
                if not batch:
                    break
        # Dedupe by objectID
        by_id: dict[str, dict[str, Any]] = {}
        for h in hits:
            oid = str(h.get("objectID") or h.get("id") or "").strip()
            if oid:
                by_id[oid] = h
        return list(by_id.values())

    @staticmethod
    def _fetch_stand_detail(directory_url: str, stand_id: str, edition: int) -> dict[str, Any]:
        url = EASYFAIRS_STAND_DETAIL.format(stand_id=stand_id, edition=edition)
        with httpx.Client(timeout=45.0, follow_redirects=True) as client:
            resp = client.get(url, headers=ExpoDirectoryScraper._headers(directory_url))
            if resp.status_code >= 400:
                return {}
            data = resp.json()
            return data if isinstance(data, dict) else {}

    @staticmethod
    def _description_text(detail: dict[str, Any]) -> str:
        desc = detail.get("description")
        if isinstance(desc, dict):
            parts = [str(v) for v in desc.values() if v]
            return "\n".join(parts)
        return str(desc or "")

    @staticmethod
    def _extract_website(detail: dict[str, Any]) -> str:
        for key in ("websiteUrl", "website", "url", "companyWebsite"):
            val = detail.get(key)
            if isinstance(val, dict):
                val = val.get("en") or next((v for v in val.values() if v), None)
            url = str(val or "").strip()
            if url.startswith("http"):
                return url
            if url.startswith("www."):
                return "https://" + url
        return ""

    @staticmethod
    def _scrape_website_emails(website: str, *, timeout: float = 20.0) -> list[str]:
        url = str(website or "").strip()
        if not url.startswith("http"):
            return []
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                resp = client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; VoxBulkExpoScraper/1.0)",
                        "Accept": "text/html",
                    },
                )
                if resp.status_code >= 400:
                    return []
                emails = ExpoDirectoryScraper.clean_emails(resp.text or "")
                # Prefer contact page if homepage has none
                if emails:
                    return emails
                for path in ("/contact", "/contact-us", "/about", "/about-us"):
                    try:
                        cr = client.get(urljoin(url if url.endswith("/") else url + "/", path.lstrip("/")))
                        if cr.status_code < 400:
                            more = ExpoDirectoryScraper.clean_emails(cr.text or "")
                            if more:
                                return more
                    except Exception:
                        continue
                return []
        except Exception:
            return []

    @staticmethod
    def _stand_to_contacts(
        *,
        directory_url: str,
        hit: dict[str, Any],
        detail: dict[str, Any],
        follow_websites: bool,
    ) -> list[dict[str, Any]]:
        stand_id = str(detail.get("id") or hit.get("objectID") or "").strip()
        name = str(detail.get("name") or hit.get("name") or "").strip()
        event = str(detail.get("eventName") or hit.get("eventName") or "").strip()
        edition = int(detail.get("containerId") or hit.get("containerId") or 0)
        website = ExpoDirectoryScraper._extract_website(detail)
        desc = ExpoDirectoryScraper._description_text(detail)
        emails = ExpoDirectoryScraper.clean_emails(desc)
        if follow_websites and website and not emails:
            emails = ExpoDirectoryScraper._scrape_website_emails(website)

        parsed = urlparse(directory_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path.rstrip("/") or "/exhibitors"
        # Keep directory root (/exhibitors) for profile links
        if not path.endswith("exhibitors") and "/exhibitors" in path:
            path = path[: path.find("/exhibitors") + len("/exhibitors")]
        elif "exhibitors" not in path:
            path = "/exhibitors"
        profile_url = f"{base}{path}/{ExpoDirectoryScraper._slugify(name)}-{stand_id}/"

        if not emails:
            # Keep company as a no-email row? Import requires email — skip.
            return []

        out: list[dict[str, Any]] = []
        for email in emails:
            out.append(
                {
                    "email": email,
                    "first_name": "",
                    "last_name": "",
                    "company_name": name,
                    "job_title": "Exhibitor",
                    "sector": "expo",
                    "country_code": "GB",
                    "website": website,
                    "profile_url": profile_url,
                    "event_name": event,
                    "stand_number": str(detail.get("standNumber") or hit.get("standNumber") or ""),
                    "stand_id": stand_id,
                    "edition_id": edition,
                    "source": "expo_directory",
                    "profile_json": {
                        "expo_url": directory_url,
                        "profile_url": profile_url,
                        "website": website,
                        "event_name": event,
                        "stand_number": detail.get("standNumber") or hit.get("standNumber"),
                        "stand_id": stand_id,
                    },
                }
            )
        return out

    @staticmethod
    def _emit_progress(cb: ProgressCallback | None, payload: dict[str, Any]) -> None:
        if not cb:
            return
        try:
            data = dict(payload)
            data.setdefault("heartbeat_at", datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z")
            cb(data)
        except ScrapeAborted:
            raise
        except Exception:
            logger.debug("expo_scrape_progress_callback_failed", exc_info=True)

    @staticmethod
    def scrape_easyfairs(
        directory_url: str,
        *,
        follow_websites: bool = True,
        max_stands: int = 500,
        workers: int = 10,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        ExpoDirectoryScraper._emit_progress(
            progress_callback,
            {
                "phase": "listing",
                "message": "Detecting Easyfairs editions…",
                "provider": "easyfairs",
                "follow_websites": bool(follow_websites),
                "stands_total": 0,
                "stands_done": 0,
                "stands_with_email": 0,
                "emails_found": 0,
                "errors": 0,
            },
        )
        editions = ExpoDirectoryScraper.detect_easyfairs_editions(directory_url)
        if not editions:
            raise ExpoDirectoryScraperError(
                "This URL does not look like an Easyfairs exhibitor directory "
                "(or the widget loader is unavailable)."
            )
        ExpoDirectoryScraper._emit_progress(
            progress_callback,
            {
                "phase": "listing",
                "message": "Listing stands from Easyfairs…",
                "provider": "easyfairs",
                "follow_websites": bool(follow_websites),
                "editions": editions,
                "stands_total": 0,
                "stands_done": 0,
                "stands_with_email": 0,
                "emails_found": 0,
                "errors": 0,
            },
        )
        hits = ExpoDirectoryScraper._search_stands(directory_url, editions)
        hits = hits[: max(1, min(int(max_stands or 500), 1000))]
        contacts: list[dict[str, Any]] = []
        stands_with_email = 0
        errors = 0
        stands_done = 0
        total = len(hits)
        ExpoDirectoryScraper._emit_progress(
            progress_callback,
            {
                "phase": "stands",
                "message": f"Scanning {total} stands…",
                "provider": "easyfairs",
                "follow_websites": bool(follow_websites),
                "editions": editions,
                "stands_total": total,
                "stands_done": 0,
                "stands_with_email": 0,
                "emails_found": 0,
                "errors": 0,
            },
        )

        def _one(hit: dict[str, Any]) -> list[dict[str, Any]]:
            stand_id = str(hit.get("objectID") or "").strip()
            edition = int(hit.get("containerId") or 0)
            if not stand_id or not edition:
                return []
            detail = ExpoDirectoryScraper._fetch_stand_detail(directory_url, stand_id, edition)
            if not detail:
                detail = {
                    "id": stand_id,
                    "name": hit.get("name"),
                    "eventName": hit.get("eventName"),
                    "containerId": edition,
                    "standNumber": hit.get("standNumber"),
                    "description": hit.get("description") or {},
                }
            return ExpoDirectoryScraper._stand_to_contacts(
                directory_url=directory_url,
                hit=hit,
                detail=detail,
                follow_websites=follow_websites,
            )

        with ThreadPoolExecutor(max_workers=max(1, min(int(workers or 10), 16))) as pool:
            futs = [pool.submit(_one, h) for h in hits]
            for fut in as_completed(futs):
                try:
                    rows = fut.result()
                    if rows:
                        stands_with_email += 1
                        contacts.extend(rows)
                except Exception:
                    errors += 1
                    logger.exception("expo_stand_scrape_failed")
                stands_done += 1
                # Dedupe emails for live count
                seen_emails = {str(c.get("email") or "").lower() for c in contacts if c.get("email")}
                ExpoDirectoryScraper._emit_progress(
                    progress_callback,
                    {
                        "phase": "stands",
                        "message": f"Scanning stands {stands_done}/{total}…",
                        "provider": "easyfairs",
                        "follow_websites": bool(follow_websites),
                        "editions": editions,
                        "stands_total": total,
                        "stands_done": stands_done,
                        "stands_with_email": stands_with_email,
                        "emails_found": len(seen_emails),
                        "errors": errors,
                    },
                )

        # Dedupe by email (first company wins)
        by_email: dict[str, dict[str, Any]] = {}
        for c in contacts:
            email = str(c.get("email") or "").lower()
            if email and email not in by_email:
                by_email[email] = c

        result = {
            "ok": True,
            "provider": "easyfairs",
            "editions": editions,
            "stands_found": len(hits),
            "stands_with_email": stands_with_email,
            "emails_found": len(by_email),
            "errors": errors,
            "contacts": list(by_email.values()),
        }
        ExpoDirectoryScraper._emit_progress(
            progress_callback,
            {
                "phase": "done",
                "message": "Scrape finished — saving results…",
                "provider": "easyfairs",
                "follow_websites": bool(follow_websites),
                "stands_total": total,
                "stands_done": total,
                "stands_with_email": stands_with_email,
                "emails_found": len(by_email),
                "errors": errors,
            },
        )
        return result

    @staticmethod
    def scrape_html_directory(
        directory_url: str,
        *,
        follow_websites: bool = True,
        max_pages: int = 300,
        workers: int = 8,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Generic fallback: collect /exhibitors/* links from the listing HTML, then extract emails."""
        ExpoDirectoryScraper._emit_progress(
            progress_callback,
            {
                "phase": "listing",
                "message": "Fetching directory HTML…",
                "provider": "html",
                "follow_websites": bool(follow_websites),
                "stands_total": 0,
                "stands_done": 0,
                "stands_with_email": 0,
                "emails_found": 0,
                "errors": 0,
            },
        )
        headers = ExpoDirectoryScraper._headers(directory_url)
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            resp = client.get(directory_url, headers=headers)
            if resp.status_code >= 400:
                raise ExpoDirectoryScraperError(f"Could not fetch directory ({resp.status_code})")
            html = resp.text or ""

        parsed = urlparse(directory_url)
        uniq = ExpoDirectoryScraper._collect_exhibitor_profile_links(
            directory_url, html, max_pages=max_pages
        )
        # ASP Events / SHOWOFF A–Z lists often hide profiles behind azletter pages
        if not uniq and (
            "azletter=" in html.lower()
            or "m-exhibitors-list" in html.lower()
            or "showoff" in html.lower()
            or "themes.asp.events" in html.lower()
        ):
            asp = ExpoDirectoryScraper.scrape_asp_events(
                directory_url,
                follow_websites=follow_websites,
                max_stands=max_pages,
                progress_callback=progress_callback,
            )
            if asp is not None:
                return asp
            # Re-collect after letter crawl helper
            uniq = ExpoDirectoryScraper._asp_collect_profile_links(
                directory_url, max_pages=max_pages, headers=headers
            )
        if not uniq:
            # Still extract any emails visible on the listing itself
            listing_emails = ExpoDirectoryScraper.clean_emails(html)
            contacts = [
                {
                    "email": e,
                    "company_name": "",
                    "job_title": "Exhibitor",
                    "sector": "expo",
                    "source": "expo_directory",
                    "profile_json": {"expo_url": directory_url},
                }
                for e in listing_emails
            ]
            return {
                "ok": True,
                "provider": "html",
                "stands_found": 0,
                "stands_with_email": len(contacts),
                "emails_found": len(contacts),
                "errors": 0,
                "contacts": contacts,
                "warning": "No exhibitor profile links found in HTML — only listing-page emails were extracted. "
                "JS-heavy directories need Easyfairs or an Apify actor.",
            }

        contacts: list[dict[str, Any]] = []
        stands_with_email = 0
        errors = 0
        stands_done = 0
        total = len(uniq)
        ExpoDirectoryScraper._emit_progress(
            progress_callback,
            {
                "phase": "stands",
                "message": f"Scanning {total} exhibitor pages…",
                "provider": "html",
                "follow_websites": bool(follow_websites),
                "stands_total": total,
                "stands_done": 0,
                "stands_with_email": 0,
                "emails_found": 0,
                "errors": 0,
            },
        )

        def _page(url: str) -> list[dict[str, Any]]:
            with httpx.Client(timeout=40.0, follow_redirects=True) as client:
                r = client.get(url, headers=headers)
                if r.status_code >= 400:
                    return []
                text = r.text or ""
            emails = ExpoDirectoryScraper.clean_emails(text)
            title = ""
            mt = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.I | re.S)
            if mt:
                title = re.sub(r"<[^>]+>", "", mt.group(1)).strip()
            websites = re.findall(
                r"""href=["'](https?://(?!(?:www\.)?"""
                + re.escape(parsed.netloc)
                + r""")[^"']+)["']""",
                text,
                re.I,
            )
            # Prefer explicit "Visit website" / contact buttons (ASP Events)
            preferred = re.findall(
                r"""(?:Visit\s+website|button__website|contact-us)[^>]{0,120}href=["'](https?://[^"']+)["']"""
                r"""|href=["'](https?://[^"']+)["'][^>]{0,80}(?:Visit\s+website|button__website)""",
                text,
                re.I,
            )
            flat_pref = [p for pair in preferred for p in (pair if isinstance(pair, tuple) else (pair,)) if p]
            website = ""
            for w in flat_pref + websites:
                low = w.lower()
                if parsed.netloc.lower() in low:
                    continue
                if any(
                    x in low
                    for x in (
                        "facebook", "linkedin", "twitter", "instagram", "youtube",
                        "google", "asp.events", "closerstill", "ukimedia",
                    )
                ):
                    continue
                website = w
                break
            if follow_websites and website and not emails:
                emails = ExpoDirectoryScraper._scrape_website_emails(website)
            if not emails:
                return []
            return [
                {
                    "email": e,
                    "company_name": title,
                    "job_title": "Exhibitor",
                    "sector": "expo",
                    "website": website,
                    "profile_url": url,
                    "source": "expo_directory",
                    "profile_json": {"expo_url": directory_url, "profile_url": url, "website": website},
                }
                for e in emails
            ]

        with ThreadPoolExecutor(max_workers=max(1, min(int(workers or 8), 12))) as pool:
            futs = [pool.submit(_page, u) for u in uniq]
            for fut in as_completed(futs):
                try:
                    rows = fut.result()
                    if rows:
                        stands_with_email += 1
                        contacts.extend(rows)
                except Exception:
                    errors += 1
                stands_done += 1
                seen_emails = {str(c.get("email") or "").lower() for c in contacts if c.get("email")}
                ExpoDirectoryScraper._emit_progress(
                    progress_callback,
                    {
                        "phase": "stands",
                        "message": f"Scanning pages {stands_done}/{total}…",
                        "provider": "html",
                        "follow_websites": bool(follow_websites),
                        "stands_total": total,
                        "stands_done": stands_done,
                        "stands_with_email": stands_with_email,
                        "emails_found": len(seen_emails),
                        "errors": errors,
                    },
                )

        by_email: dict[str, dict[str, Any]] = {}
        for c in contacts:
            email = str(c.get("email") or "").lower()
            if email and email not in by_email:
                by_email[email] = c

        return {
            "ok": True,
            "provider": "html",
            "stands_found": len(uniq),
            "stands_with_email": stands_with_email,
            "emails_found": len(by_email),
            "errors": errors,
            "contacts": list(by_email.values()),
        }

    @staticmethod
    def _is_exhibitor_profile_path(path: str) -> bool:
        p = (path or "").rstrip("/")
        low = p.lower()
        if low.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js", ".pdf")):
            return False
        # /exhibitors/company-slug or /exhibitor/company-slug (not the list root)
        for token in ("/exhibitors/", "/exhibitor/"):
            if token in low:
                # must have something after the token
                after = low.split(token, 1)[-1]
                if after and after not in {"list", "directory", "hub", "e-zone"}:
                    return True
        return False

    @staticmethod
    def _collect_exhibitor_profile_links(
        directory_url: str,
        html: str,
        *,
        max_pages: int = 500,
    ) -> list[str]:
        parsed = urlparse(directory_url)
        links: list[str] = []
        for h in re.findall(r"""href=["']([^"']+)["']""", html or "", re.I):
            full = urljoin(directory_url, h).split("#")[0].split("?")[0]
            p = urlparse(full)
            if p.netloc and p.netloc.lower() != parsed.netloc.lower():
                continue
            if ExpoDirectoryScraper._is_exhibitor_profile_path(p.path):
                links.append(full)
        return sorted(set(links))[: max(1, min(int(max_pages or 500), 2000))]

    @staticmethod
    def _asp_collect_profile_links(
        directory_url: str,
        *,
        max_pages: int = 500,
        headers: dict[str, str] | None = None,
    ) -> list[str]:
        """Crawl ASP Events / SHOWOFF A–Z exhibitor-list pages for profile URLs."""
        parsed = urlparse(directory_url)
        list_url = directory_url.split("?")[0].split("#")[0]
        # Prefer exhibitor-list path when present
        if "exhibitor-list" not in list_url.lower() and "exhibitors" not in urlparse(list_url).path.lower():
            list_url = f"{parsed.scheme}://{parsed.netloc}/exhibitor-list"
        headers = headers or ExpoDirectoryScraper._headers(directory_url)
        letters = [*"ABCDEFGHIJKLMNOPQRSTUVWXYZ", "0-9", ""]
        found: set[str] = set()
        with httpx.Client(timeout=45.0, follow_redirects=True) as client:
            for letter in letters:
                if len(found) >= max(1, min(int(max_pages or 500), 2000)):
                    break
                url = list_url if letter == "" else f"{list_url}?azletter={letter}"
                try:
                    resp = client.get(url, headers=headers)
                    if resp.status_code >= 400:
                        continue
                    for link in ExpoDirectoryScraper._collect_exhibitor_profile_links(
                        list_url, resp.text or "", max_pages=2000
                    ):
                        found.add(link)
                except Exception:
                    continue
        return sorted(found)[: max(1, min(int(max_pages or 500), 2000))]

    @staticmethod
    def scrape_asp_events(
        directory_url: str,
        *,
        follow_websites: bool = True,
        max_stands: int = 500,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any] | None:
        """ASP Events / SHOWOFF exhibitor-list (A–Z) → profile pages → company websites."""
        headers = ExpoDirectoryScraper._headers(directory_url)
        try:
            with httpx.Client(timeout=45.0, follow_redirects=True) as client:
                resp = client.get(directory_url, headers=headers)
                if resp.status_code >= 400:
                    return None
                html = resp.text or ""
        except Exception:
            return None
        low = html.lower()
        looks_asp = (
            "azletter=" in low
            or "m-exhibitors-list" in low
            or "showoff" in low
            or "themes.asp.events" in low
            or "exhibitor-list" in urlparse(directory_url).path.lower()
        )
        if not looks_asp:
            return None

        ExpoDirectoryScraper._emit_progress(
            progress_callback,
            {
                "phase": "listing",
                "message": "ASP Events directory — scanning A–Z exhibitor lists…",
                "provider": "asp_events",
                "follow_websites": bool(follow_websites),
                "stands_total": 0,
                "stands_done": 0,
                "stands_with_email": 0,
                "emails_found": 0,
                "errors": 0,
            },
        )
        uniq = ExpoDirectoryScraper._asp_collect_profile_links(
            directory_url, max_pages=max_stands, headers=headers
        )
        if not uniq:
            return None

        # Reuse HTML page scanner by temporarily building a mini directory result path
        # Call scrape_html_directory logic on collected links via internal scan
        parsed = urlparse(directory_url)
        contacts: list[dict[str, Any]] = []
        stands_with_email = 0
        errors = 0
        stands_done = 0
        total = len(uniq)
        ExpoDirectoryScraper._emit_progress(
            progress_callback,
            {
                "phase": "stands",
                "message": f"ASP Events · scanning {total} exhibitor pages…",
                "provider": "asp_events",
                "follow_websites": bool(follow_websites),
                "stands_total": total,
                "stands_done": 0,
                "stands_with_email": 0,
                "emails_found": 0,
                "errors": 0,
            },
        )

        def _page(url: str) -> list[dict[str, Any]]:
            with httpx.Client(timeout=40.0, follow_redirects=True) as client:
                r = client.get(url, headers=headers)
                if r.status_code >= 400:
                    return []
                text = r.text or ""
            emails = ExpoDirectoryScraper.clean_emails(text)
            title = ""
            for pat in (
                r'class=["\'][^"\']*exhibitor-entry__item__header__title[^"\']*["\'][^>]*>\s*<[^>]+>(.*?)</',
                r'item__header__title[^>]*>\s*<a[^>]*>(.*?)</a>',
                r'property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']',
                r"<h1[^>]*>(.*?)</h1>",
            ):
                mt = re.search(pat, text, re.I | re.S)
                if mt:
                    title = re.sub(r"<[^>]+>", "", mt.group(1)).strip()
                    title = re.sub(r"\s+", " ", title)
                    if title and "exhibitor" not in title.lower()[:12]:
                        break
                    if title and len(title) < 80:
                        break
                    title = title or ""
            if title.lower().startswith("px ") or "exhibitors" == title.lower():
                title = ""
            if not title:
                mt = re.search(
                    r'item__header__title__link[^>]*>(.*?)</a>',
                    text,
                    re.I | re.S,
                )
                if mt:
                    title = re.sub(r"<[^>]+>", "", mt.group(1)).strip()
            # Fallback: last path segment as company slug
            if not title:
                slug = urlparse(url).path.rstrip("/").split("/")[-1]
                title = slug.replace("-", " ").strip()
                title = re.sub(r"\s+\d+$", "", title).title()
            website = ""
            mweb = re.search(
                r"button__website[\s\S]{0,260}?href=['\"](https?://[^'\"]+)['\"]"
                r"|href=['\"](https?://[^'\"]+)['\"][^>]*>\s*Visit website",
                text,
                re.I,
            )
            if mweb:
                website = mweb.group(1) or mweb.group(2) or ""
            if not website:
                for w in re.findall(r"""href=["'](https?://[^"']+)["']""", text, re.I):
                    low_w = w.lower()
                    if parsed.netloc.lower() in low_w:
                        continue
                    if any(
                        x in low_w
                        for x in (
                            "facebook", "linkedin", "twitter", "instagram", "youtube",
                            "google", "asp.events", "closerstill", "ukimedia", "typekit",
                        )
                    ):
                        continue
                    website = w
                    break
            if follow_websites and website and not emails:
                emails = ExpoDirectoryScraper._scrape_website_emails(website)
            if not emails:
                return []
            return [
                {
                    "email": e,
                    "company_name": title,
                    "job_title": "Exhibitor",
                    "sector": "expo",
                    "website": website,
                    "profile_url": url,
                    "source": "expo_asp_events",
                    "profile_json": {
                        "expo_url": directory_url,
                        "profile_url": url,
                        "website": website,
                        "provider": "asp_events",
                    },
                }
                for e in emails
            ]

        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = [pool.submit(_page, u) for u in uniq]
            for fut in as_completed(futs):
                try:
                    rows = fut.result()
                    if rows:
                        stands_with_email += 1
                        contacts.extend(rows)
                except Exception:
                    errors += 1
                stands_done += 1
                seen_emails = {str(c.get("email") or "").lower() for c in contacts if c.get("email")}
                ExpoDirectoryScraper._emit_progress(
                    progress_callback,
                    {
                        "phase": "stands",
                        "message": f"ASP Events · {stands_done}/{total} pages…",
                        "provider": "asp_events",
                        "follow_websites": bool(follow_websites),
                        "stands_total": total,
                        "stands_done": stands_done,
                        "stands_with_email": stands_with_email,
                        "emails_found": len(seen_emails),
                        "errors": errors,
                    },
                )

        by_email: dict[str, dict[str, Any]] = {}
        for c in contacts:
            email = str(c.get("email") or "").lower()
            if email and email not in by_email:
                by_email[email] = c
        if not by_email:
            return {
                "ok": True,
                "provider": "asp_events",
                "stands_found": len(uniq),
                "stands_with_email": 0,
                "emails_found": 0,
                "errors": errors,
                "contacts": [],
                "warning": "Found exhibitor profiles but no public emails "
                "(enable “Also scrape company websites”).",
            }
        return {
            "ok": True,
            "provider": "asp_events",
            "stands_found": len(uniq),
            "stands_with_email": stands_with_email,
            "emails_found": len(by_email),
            "errors": errors,
            "contacts": list(by_email.values()),
        }

    @staticmethod
    def scrape_reed_algolia(
        directory_url: str,
        *,
        max_stands: int = 500,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any] | None:
        """Reed Expo / RX exhibitor directories (WTM, etc.) via public Algolia search index.

        Page embeds algoliaConfig + eventId; index name is ``{eventId}-index``.
        """
        headers = ExpoDirectoryScraper._headers(directory_url)
        try:
            with httpx.Client(timeout=45.0, follow_redirects=True) as client:
                resp = client.get(directory_url.split("#")[0], headers=headers)
                if resp.status_code >= 400:
                    return None
                html = resp.text or ""
        except Exception:
            return None

        decoded = (
            (html or "")
            .replace("\\x22", '"')
            .replace("\\u0022", '"')
            .replace("\\u002D", "-")
            .replace("\\/", "/")
        )
        api_keys = re.findall(r'"apiKey"\s*:\s*"([a-zA-Z0-9]{16,})"', decoded)
        app_ids = re.findall(r'"(?:appId|applicationID)"\s*:\s*"([A-Z0-9]{6,})"', decoded)
        event_ids = re.findall(r'"eventId"\s*:\s*"(evt-[a-f0-9\-]+)"', decoded, re.I)
        if not event_ids:
            event_ids = re.findall(r"(evt-[a-f0-9]{8}-[a-f0-9\-]+)", decoded, re.I)
        edition_ids = re.findall(
            r'(?:eventEditionId\s*=\s*"|\"eventEditionId\"\s*:\s*")(eve-[a-f0-9\-]+)"',
            decoded,
            re.I,
        )
        if not edition_ids:
            edition_ids = re.findall(r"(eve-[a-f0-9]{8}-[a-f0-9\-]+)", decoded, re.I)

        looks_rx = (
            "algoliaConfig" in decoded
            or "reedexpo.com" in decoded.lower()
            or "exhibitor-directory" in decoded.lower()
            or "css-components.rxweb" in decoded.lower()
        )
        if not (looks_rx and api_keys and app_ids and event_ids):
            return None

        api_key = api_keys[0]
        app_id = app_ids[0]
        event_id = event_ids[0]
        edition_id = edition_ids[0] if edition_ids else ""
        index_name = f"{event_id}-index"

        ExpoDirectoryScraper._emit_progress(
            progress_callback,
            {
                "phase": "listing",
                "message": "Reed Expo directory — fetching Algolia exhibitors…",
                "provider": "reed_algolia",
                "stands_total": 0,
                "stands_done": 0,
                "stands_with_email": 0,
                "emails_found": 0,
                "errors": 0,
            },
        )

        caps = max(1, min(int(max_stands or 500), 2000))
        hits_per_page = 100
        page = 0
        all_hits: list[dict[str, Any]] = []
        algolia_headers = {
            "X-Algolia-Application-Id": app_id,
            "X-Algolia-API-Key": api_key,
            "Content-Type": "application/json",
            "User-Agent": headers.get("User-Agent", "VoxBulkExpoScraper/1.0"),
        }
        filters = 'recordType:exhibitor'
        if edition_id:
            filters = f'eventEditionId:"{edition_id}" AND recordType:exhibitor'

        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            while len(all_hits) < caps and page < 50:
                endpoint = f"https://{app_id}-dsn.algolia.net/1/indexes/{index_name}/query"
                try:
                    params = urlencode(
                        {
                            "query": "",
                            "hitsPerPage": hits_per_page,
                            "page": page,
                            "filters": filters,
                        }
                    )
                    r = client.post(
                        endpoint,
                        headers=algolia_headers,
                        json={"params": params},
                    )
                except Exception:
                    break
                if r.status_code >= 400:
                    # Retry without edition filter if it fails
                    if page == 0 and edition_id:
                        params = urlencode(
                            {
                                "query": "",
                                "hitsPerPage": hits_per_page,
                                "page": page,
                                "filters": "recordType:exhibitor",
                            }
                        )
                        r = client.post(
                            endpoint,
                            headers=algolia_headers,
                            json={"params": params},
                        )
                    if r.status_code >= 400:
                        logger.warning(
                            "reed_algolia_query_failed status=%s body=%s",
                            r.status_code,
                            (r.text or "")[:200],
                        )
                        return None
                data = r.json() if r.content else {}
                batch = [h for h in (data.get("hits") or []) if isinstance(h, dict)]
                if not batch:
                    break
                # Prefer current edition when unfiltered
                if edition_id:
                    filtered = [
                        h for h in batch
                        if str(h.get("eventEditionId") or "") == edition_id
                    ]
                    if filtered:
                        batch = filtered
                all_hits.extend(batch)
                nb_pages = int(data.get("nbPages") or 0)
                ExpoDirectoryScraper._emit_progress(
                    progress_callback,
                    {
                        "phase": "listing",
                        "message": f"Reed Expo · loaded {len(all_hits)} exhibitors…",
                        "provider": "reed_algolia",
                        "stands_total": min(caps, int(data.get("nbHits") or len(all_hits))),
                        "stands_done": len(all_hits),
                        "stands_with_email": sum(
                            1 for h in all_hits if str(h.get("email") or "").strip()
                        ),
                        "emails_found": len(
                            {
                                str(h.get("email") or "").strip().lower()
                                for h in all_hits
                                if str(h.get("email") or "").strip()
                            }
                        ),
                        "errors": 0,
                    },
                )
                page += 1
                if page >= nb_pages:
                    break

        by_email: dict[str, dict[str, Any]] = {}
        for hit in all_hits[:caps]:
            email = str(hit.get("email") or "").strip().lower()
            if not email or "@" not in email:
                continue
            if any(j in email for j in _JUNK_EMAIL_SUBSTR):
                continue
            company = str(
                hit.get("exhibitorName") or hit.get("companyName") or ""
            ).strip()
            website = str(hit.get("website") or "").strip()
            by_email[email] = {
                "email": email,
                "company_name": company,
                "job_title": "Exhibitor",
                "sector": "expo",
                "website": website,
                "country_code": "",
                "source": "expo_reed_algolia",
                "profile_json": {
                    "expo_url": directory_url,
                    "website": website,
                    "stand_number": hit.get("standReference"),
                    "provider": "reed_algolia",
                    "event_id": event_id,
                    "event_edition_id": hit.get("eventEditionId") or edition_id,
                    "organisation_guid": hit.get("organisationGuid"),
                },
            }

        if not by_email:
            return None

        ExpoDirectoryScraper._emit_progress(
            progress_callback,
            {
                "phase": "done",
                "message": f"Reed Expo · {len(by_email)} emails",
                "provider": "reed_algolia",
                "stands_total": len(all_hits),
                "stands_done": len(all_hits),
                "stands_with_email": len(by_email),
                "emails_found": len(by_email),
                "errors": 0,
            },
        )
        return {
            "ok": True,
            "provider": "reed_algolia",
            "stands_found": len(all_hits),
            "stands_with_email": len(by_email),
            "emails_found": len(by_email),
            "errors": 0,
            "contacts": list(by_email.values()),
        }

    @staticmethod
    def _looks_like_spa_shell(html: str) -> bool:
        low = (html or "").lower()
        if "/assets/" in low and ".js" in low and ("<div id=\"root\"" in low or "<div id=\"app\"" in low):
            return True
        if "__next_data__" in low or "/assets/index-" in low:
            return True
        # Tiny HTML shells with a big JS bundle and almost no exhibitor links
        if len(html or "") < 20000 and re.search(r'/assets/[^"\']+\.js', html or "", re.I):
            return True
        return False

    @staticmethod
    def scrape_spa_supabase(
        directory_url: str,
        *,
        max_stands: int = 500,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any] | None:
        """JS SPA exhibitor sites that load contacts from public Supabase REST.

        Example: takeawayexpo.co.uk/exhibitors → exhibitor_contacts (+ exhibitors).
        Returns None when this pattern is not detected.
        """
        ExpoDirectoryScraper._emit_progress(
            progress_callback,
            {
                "phase": "listing",
                "message": "Detecting SPA / API directory…",
                "provider": "spa",
                "stands_total": 0,
                "stands_done": 0,
                "stands_with_email": 0,
                "emails_found": 0,
                "errors": 0,
            },
        )
        headers = ExpoDirectoryScraper._headers(directory_url)
        try:
            with httpx.Client(timeout=45.0, follow_redirects=True) as client:
                resp = client.get(directory_url, headers=headers)
                if resp.status_code >= 400:
                    return None
                html = resp.text or ""
                if not ExpoDirectoryScraper._looks_like_spa_shell(html):
                    return None
                script_srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, re.I)
                js_url = None
                for src in script_srcs:
                    if "/assets/" in src and src.endswith(".js"):
                        js_url = urljoin(directory_url, src)
                        break
                if not js_url:
                    return None
                js_resp = client.get(js_url, headers=headers)
                if js_resp.status_code >= 400:
                    return None
                js = js_resp.text or ""
        except Exception:
            return None

        hosts = sorted(set(re.findall(r"https://[a-z0-9]+\.supabase\.co", js, re.I)))
        keys = sorted(
            set(
                re.findall(
                    r"eyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}",
                    js,
                )
            )
        )
        if not hosts or not keys:
            return None

        ExpoDirectoryScraper._emit_progress(
            progress_callback,
            {
                "phase": "listing",
                "message": "Fetching exhibitor contacts from site API…",
                "provider": "spa_supabase",
                "stands_total": 0,
                "stands_done": 0,
                "stands_with_email": 0,
                "emails_found": 0,
                "errors": 0,
            },
        )

        contact_rows: list[dict[str, Any]] = []
        exhibitor_by_id: dict[str, dict[str, Any]] = {}
        used_host = ""
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            for host in hosts:
                for key in keys[:3]:
                    api_headers = {
                        **headers,
                        "Accept": "application/json",
                        "apikey": key,
                        "Authorization": f"Bearer {key}",
                    }
                    try:
                        c_resp = client.get(
                            f"{host}/rest/v1/exhibitor_contacts",
                            headers=api_headers,
                            params={"select": "*", "limit": str(max(1, min(int(max_stands or 500), 2000)))},
                        )
                        if c_resp.status_code >= 400:
                            continue
                        data = c_resp.json()
                        if not isinstance(data, list) or not data:
                            continue
                        # Need at least one email-like field
                        sample = data[0] if isinstance(data[0], dict) else {}
                        if not any(k in sample for k in ("email", "contact_email", "Email")):
                            # still accept if any row has @
                            blob = json.dumps(data[:5], ensure_ascii=False)
                            if "@" not in blob:
                                continue
                        contact_rows = [r for r in data if isinstance(r, dict)]
                        used_host = host
                        try:
                            e_resp = client.get(
                                f"{host}/rest/v1/exhibitors",
                                headers=api_headers,
                                params={"select": "id,name,website,slug,booth_number,category", "limit": "2000"},
                            )
                            if e_resp.status_code < 400:
                                for ex in e_resp.json() or []:
                                    if isinstance(ex, dict) and ex.get("id"):
                                        exhibitor_by_id[str(ex["id"])] = ex
                        except Exception:
                            pass
                        break
                    except Exception:
                        continue
                if contact_rows:
                    break

        if not contact_rows:
            return None

        by_email: dict[str, dict[str, Any]] = {}
        for row in contact_rows[: max(1, min(int(max_stands or 500), 2000))]:
            email = str(row.get("email") or row.get("contact_email") or "").strip().lower()
            if not email or "@" not in email:
                continue
            for junk in _JUNK_EMAIL_SUBSTR:
                if junk in email:
                    email = ""
                    break
            if not email:
                continue
            ex_id = str(row.get("exhibitor_id") or "")
            ex = exhibitor_by_id.get(ex_id) or {}
            full_name = str(row.get("full_name") or row.get("name") or "").strip()
            first = ""
            last = ""
            if full_name:
                parts = full_name.split(None, 1)
                first = parts[0]
                last = parts[1] if len(parts) > 1 else ""
            company = str(ex.get("name") or row.get("company_name") or "").strip()
            website = str(ex.get("website") or row.get("website") or "").strip()
            by_email[email] = {
                "email": email,
                "first_name": first,
                "last_name": last,
                "company_name": company,
                "job_title": str(row.get("job_title") or "Exhibitor").strip() or "Exhibitor",
                "sector": str(ex.get("category") or "expo").strip() or "expo",
                "country_code": "GB",
                "source": "expo_spa_supabase",
                "profile_json": {
                    "expo_url": directory_url,
                    "website": website,
                    "stand_number": ex.get("booth_number"),
                    "slug": ex.get("slug"),
                    "provider": "spa_supabase",
                    "api_host": used_host,
                },
            }

        contacts = list(by_email.values())
        if not contacts:
            return None

        ExpoDirectoryScraper._emit_progress(
            progress_callback,
            {
                "phase": "done",
                "message": f"SPA API · {len(contacts)} emails",
                "provider": "spa_supabase",
                "stands_total": len(contacts),
                "stands_done": len(contacts),
                "stands_with_email": len(contacts),
                "emails_found": len(contacts),
                "errors": 0,
            },
        )
        return {
            "ok": True,
            "provider": "spa_supabase",
            "stands_found": len(contacts),
            "stands_with_email": len(contacts),
            "emails_found": len(contacts),
            "errors": 0,
            "contacts": contacts,
        }

    @staticmethod
    def scrape(
        directory_url: str,
        *,
        follow_websites: bool = True,
        max_stands: int = 500,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        url = str(directory_url or "").strip()
        if not url.startswith("http"):
            raise ExpoDirectoryScraperError("Enter a valid exhibitor directory URL (https://…)")
        editions = ExpoDirectoryScraper.detect_easyfairs_editions(url)
        if editions:
            return ExpoDirectoryScraper.scrape_easyfairs(
                url,
                follow_websites=follow_websites,
                max_stands=max_stands,
                progress_callback=progress_callback,
            )
        # Reed Expo / RX (WTM etc.) — public Algolia index often includes emails
        reed = ExpoDirectoryScraper.scrape_reed_algolia(
            url,
            max_stands=max_stands,
            progress_callback=progress_callback,
        )
        if reed and int(reed.get("emails_found") or 0) > 0:
            return reed
        # JS SPA directories (Supabase / similar) before naive HTML crawl
        spa = ExpoDirectoryScraper.scrape_spa_supabase(
            url,
            max_stands=max_stands,
            progress_callback=progress_callback,
        )
        if spa and int(spa.get("emails_found") or 0) > 0:
            return spa
        # ASP Events / SHOWOFF A–Z exhibitor lists (Parcel+Post Expo, etc.)
        asp = ExpoDirectoryScraper.scrape_asp_events(
            url,
            follow_websites=follow_websites,
            max_stands=max_stands,
            progress_callback=progress_callback,
        )
        if asp and int(asp.get("emails_found") or 0) > 0:
            return asp
        return ExpoDirectoryScraper.scrape_html_directory(
            url,
            follow_websites=follow_websites,
            max_pages=max_stands,
            progress_callback=progress_callback,
        )
