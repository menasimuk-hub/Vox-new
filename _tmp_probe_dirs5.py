#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from urllib.parse import urljoin

import httpx

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"}
APP = "XD0U5M6Y4R"
KEY = "d5cd7d4ec26134ff4a34d736a7f9ad47"
EDITION = "eve-002a02a9-489e-4cc7-a054-455c6408ead0"


def list_indexes() -> None:
    print("=" * 80)
    print("LIST INDEXES / SEARCH")
    with httpx.Client(timeout=60.0, follow_redirects=True, headers=UA) as client:
        # list indexes
        r = client.get(
            f"https://{APP}.algolia.net/1/indexes",
            headers={"X-Algolia-Application-Id": APP, "X-Algolia-API-Key": KEY},
        )
        print("list", r.status_code, r.text[:500])
        names = []
        if r.status_code < 400:
            items = (r.json() or {}).get("items") or []
            names = [i.get("name") for i in items if isinstance(i, dict)]
            print("count", len(names))
            for n in names:
                if any(k in (n or "").lower() for k in ("exhibitor", "wtm", "london", "eve-", "evt-")):
                    print(" ", n)

        # Guess common RX index patterns
        guesses = [
            f"exhibitors_{EDITION}",
            f"exhibitors-{EDITION}",
            f"{EDITION}_exhibitors",
            f"prod_exhibitors_{EDITION}",
            f"exhibitors_eve-002a02a9-489e-4cc7-a054-455c6408ead0",
            "exhibitors",
            "wtm_london_exhibitors",
            "WTMLondon_Exhibitors",
        ]
        # also scrape index names from package JS
        js = client.get("https://css-components.rxweb-prd.com/packages/exhibitor-directory/latest/index.js").text
        found = sorted(set(re.findall(r"[\"']([a-zA-Z0-9_\-]{0,40}exhibitor[a-zA-Z0-9_\-]{0,60})[\"']", js, re.I)))
        print("js exhibitor strings", found[:40])
        found2 = sorted(set(re.findall(r"indexName[\"'=: ]{0,5}([A-Za-z0-9_\-]+)", js)))
        print("js indexName", found2[:40])
        # look for template like exhibitors_${eventEditionId}
        for m in re.finditer(r".{0,40}indexName.{0,80}", js):
            s = m.group(0)
            if "exhibitor" in s.lower() or "edition" in s.lower() or "algolia" in s.lower():
                print("ctx", s[:120])

        # From page HTML around search index
        html = client.get("https://www.wtm.com/london/en-gb/exhibitor-directory.html").text
        decoded = (
            html.replace("\\x22", '"')
            .replace("\\u002D", "-")
            .replace("\\u0022", '"')
            .replace("\\/", "/")
        )
        for pat in [
            r'"indexName"\s*:\s*"([^"]+)"',
            r'indexName"\s*:\s*"([^"]+)"',
            r'exhibitors[_-][a-zA-Z0-9_\-]+',
            r'"searchIndex"[^,]{0,80}',
            r'"exhibitorIndex"[^,]{0,80}',
        ]:
            print(pat, re.findall(pat, decoded)[:15])

        for name in guesses + found[:20]:
            if not name:
                continue
            endpoint = f"https://{APP}-dsn.algolia.net/1/indexes/{name}/query"
            rr = client.post(
                endpoint,
                headers={
                    "X-Algolia-Application-Id": APP,
                    "X-Algolia-API-Key": KEY,
                    "Content-Type": "application/json",
                },
                json={"params": "query=&hitsPerPage=2"},
            )
            if rr.status_code < 400:
                data = rr.json()
                hits = data.get("hits") or []
                print("HIT INDEX", name, "nb", data.get("nbHits"), "keys", list(hits[0].keys())[:25] if hits else [])
                if hits:
                    print(json.dumps({k: hits[0].get(k) for k in list(hits[0].keys())[:20]}, ensure_ascii=False)[:600])
                    break
            elif rr.status_code != 404:
                print("status", name, rr.status_code, rr.text[:120])


def parcel_fix() -> None:
    print("=" * 80)
    print("PARCEL REL LINKS")
    base = "https://parcelandpostexpo.com/exhibitor-list"
    with httpx.Client(timeout=45.0, follow_redirects=True, headers=UA) as client:
        html = client.get(f"{base}?azletter=A").text
        hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, re.I)
        links = []
        for h in hrefs:
            low = h.lower().split("?")[0]
            if "exhibitor" in low and not low.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
                if "/exhibitors/" in low or low.startswith("exhibitors/"):
                    links.append(urljoin(base, h).split("?")[0].split("#")[0])
        links = sorted(set(links))
        print("n", len(links), links[:10])
        if not links:
            return
        profile = links[0]
        ph = client.get(profile).text
        # website button
        m = re.search(
            r"button__website[\s\S]{0,300}?href=['\"](https?://[^'\"]+)['\"]",
            ph,
            re.I,
        )
        web = m.group(1) if m else None
        print("profile", profile, "web", web)
        if web:
            wh = client.get(web, headers={**UA, "Accept": "text/html"}, follow_redirects=True)
            emails = sorted(set(re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", wh.text or "", re.I)))
            junk = ("example.", "sentry", "wixpress", "cloudflare", "jquery", "schema.org", "webpack", "sentry.io")
            emails = [e for e in emails if not any(j in e.lower() for j in junk)]
            print("emails", emails[:20])


if __name__ == "__main__":
    list_indexes()
    parcel_fix()
