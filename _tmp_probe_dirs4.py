#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from urllib.parse import urljoin

import httpx

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}


def extract_algolia() -> None:
    print("=" * 80)
    print("ALGOLIA CONFIG")
    url = "https://www.wtm.com/london/en-gb/exhibitor-directory.html"
    with httpx.Client(timeout=60.0, follow_redirects=True, headers=UA) as client:
        html = client.get(url).text
        # Find algoliaConfig blob
        for m in re.finditer(r"algoliaConfig\\x22:\{(.*?)\}(?:,\\x22|})", html):
            chunk = m.group(0)
            print("chunk", chunk[:400])
        # Better: decode datalayer
        m = re.search(r'window\.rx\.datalayer = JSON\.parse\(decodeURIComponent\("([\s\S]*?)"\)\)', html)
        if not m:
            print("no datalayer")
        else:
            raw = m.group(1)
            text = raw.encode("utf-8").decode("unicode_escape")
            # find algolia parts
            idx = text.lower().find("algolia")
            print("datalayer algolia ctx", text[max(0, idx-50): idx+500] if idx >= 0 else "none")
            try:
                data = json.loads(text)
            except Exception as e:
                print("json fail", e)
                # try replace remaining
                data = None
            if isinstance(data, dict):
                print("top keys", list(data.keys())[:30])

        # brute extract apiKey and appId near algolia
        keys = re.findall(r"apiKey\\x22:\\x22([a-zA-Z0-9]+)\\x22", html)
        apps = re.findall(r"applicationID\\x22:\\x22([A-Z0-9]+)\\x22", html)
        apps2 = re.findall(r"appId\\x22:\\x22([A-Z0-9]+)\\x22", html)
        idxs = re.findall(r"indexName\\x22:\\x22([a-zA-Z0-9_\-]+)\\x22", html)
        print("keys", keys[:10])
        print("apps", apps[:10], apps2[:10])
        print("idxs", idxs[:20])

        # Also search in decoded form of whole page escapes
        decoded = html.encode("utf-8").decode("unicode_escape", errors="ignore")
        keys2 = re.findall(r'"apiKey"\s*:\s*"([a-zA-Z0-9]+)"', decoded)
        apps3 = re.findall(r'"(?:applicationID|appId)"\s*:\s*"([A-Z0-9]+)"', decoded)
        idxs2 = re.findall(r'"indexName"\s*:\s*"([a-zA-Z0-9_\-]+)"', decoded)
        print("decoded keys", keys2[:10])
        print("decoded apps", apps3[:10])
        print("decoded idxs", idxs2[:30])

        # Try Algolia if we have keys
        api_key = (keys or keys2 or [None])[0]
        app_id = (apps or apps2 or apps3 or [None])[0]
        index = None
        for cand in idxs + idxs2:
            if "exhibitor" in cand.lower() or "wtm" in cand.lower() or "eve-" in cand.lower():
                index = cand
                break
        if not index and (idxs or idxs2):
            index = (idxs or idxs2)[0]
        print("using", app_id, api_key, index)
        if app_id and api_key and index:
            endpoint = f"https://{app_id}-dsn.algolia.net/1/indexes/{index}/query"
            r = client.post(
                endpoint,
                headers={
                    "X-Algolia-Application-Id": app_id,
                    "X-Algolia-API-Key": api_key,
                    "Content-Type": "application/json",
                },
                json={"params": "query=&hitsPerPage=5"},
            )
            print("algolia", r.status_code, r.text[:500])
            if r.status_code < 400:
                hits = r.json().get("hits") or []
                if hits:
                    print("hit keys", list(hits[0].keys())[:40])
                    print("sample", json.dumps(hits[0], ensure_ascii=False)[:800])


def parcel_letters() -> None:
    print("=" * 80)
    print("PARCEL LETTERS + FOLLOW WEB")
    base = "https://parcelandpostexpo.com/exhibitor-list"
    with httpx.Client(timeout=45.0, follow_redirects=True, headers=UA) as client:
        letters = ["A", "B", "0-9"]
        links = set()
        for L in letters:
            html = client.get(f"{base}?azletter={L}").text
            for h in re.findall(r'href=["\']([^"\']+)["\']', html, re.I):
                if "/exhibitors/" in h and not h.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
                    links.add(urljoin(base, h).split("?")[0])
        print("links", len(links))
        for u in sorted(links)[:8]:
            print(" ", u)
        # open one profile, get website, scrape email
        if links:
            profile = sorted(links)[0]
            html = client.get(profile).text
            webs = re.findall(
                r"href=['\"](https?://[^'\"]+)['\"][^>]*>\s*Visit website",
                html,
                re.I,
            )
            if not webs:
                webs = re.findall(r"contacts__additional__button__website[\s\S]{0,200}href=['\"](https?://[^'\"]+)['\"]", html, re.I)
            print("websites", webs[:5])
            if webs:
                wh = client.get(webs[0], headers={**UA, "Accept": "text/html"})
                emails = sorted(set(re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", wh.text or "", re.I)))
                # filter junk
                junk = ("example.", "sentry", "wixpress", "cloudflare", "jquery", "schema.org")
                emails = [e for e in emails if not any(j in e.lower() for j in junk)]
                print("web emails", emails[:15], "status", wh.status_code)


if __name__ == "__main__":
    extract_algolia()
    parcel_letters()
