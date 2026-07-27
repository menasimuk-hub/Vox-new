"""Built-in expo exhibitor directory scraper (Easyfairs + generic HTML fallback).

Finds exhibitor/stand pages from a directory URL, pulls contact emails from
stand descriptions and company websites — no Apify actor required.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

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
)


class ExpoDirectoryScraperError(ValueError):
    pass


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
        base = f"{parsed.scheme}://{parsed.netloc}"
        hrefs = re.findall(r"""href=["']([^"']+)["']""", html, re.I)
        links: list[str] = []
        for h in hrefs:
            full = urljoin(directory_url, h).split("#")[0].split("?")[0]
            p = urlparse(full)
            if p.netloc != parsed.netloc:
                continue
            path = p.path.rstrip("/")
            if "/exhibitors/" in path and path.count("/") >= 2 and not path.endswith("/exhibitors"):
                links.append(full)
        uniq = sorted(set(links))[: max(1, min(int(max_pages or 300), 1000))]
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
            website = ""
            for w in websites:
                low = w.lower()
                if any(x in low for x in ("facebook", "linkedin", "twitter", "instagram", "youtube", "google")):
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
        return ExpoDirectoryScraper.scrape_html_directory(
            url,
            follow_websites=follow_websites,
            max_pages=max_stands,
            progress_callback=progress_callback,
        )
