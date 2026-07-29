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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def parcel_profile() -> None:
    print("=" * 80)
    print("PARCEL PROFILE")
    url = "https://parcelandpostexpo.com/exhibitors/addverb-technologies-bv-1"
    with httpx.Client(timeout=45.0, follow_redirects=True, headers=UA) as client:
        html = client.get(url).text
        print("len", len(html))
        emails = sorted(set(re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", html, re.I)))
        print("emails", emails[:20])
        mailtos = re.findall(r"mailto:([^\"'\s>]+)", html, re.I)
        print("mailto", mailtos[:10])
        websites = re.findall(r'href=["\'](https?://[^"\']+)["\']', html, re.I)
        webs = [w for w in websites if "parcel" not in w.lower() and "asp.events" not in w.lower()][:15]
        print("webs", webs)
        # contact section
        for key in ["email", "contact", "website", "phone", "tel:"]:
            hits = re.findall(rf".{{0,30}}{key}.{{0,60}}", html, re.I)
            print(key, hits[:6])


def wtm_search() -> None:
    print("=" * 80)
    print("WTM SEARCH")
    edition = "eve-002a02a9-489e-4cc7-a054-455c6408ead0"
    event = "evt-e8fc988b-193b-4372-a1e3-6b6ebf5b2f59"
    with httpx.Client(timeout=45.0, follow_redirects=True, headers={**UA, "Accept": "application/json"}) as client:
        # scrape page for algolia app id / api key / index
        html = client.get("https://www.wtm.com/london/en-gb/exhibitor-directory.html").text
        for pat in [
            r"algolia[^\"']{0,40}",
            r"applicationID[\"'=: ]+[A-Z0-9]+",
            r"apiKey[\"'=: ]+[a-zA-Z0-9]+",
            r"searchKey[\"'=: ]+[a-zA-Z0-9]+",
            r"indexName[\"'=: ]+[a-zA-Z0-9_\-]+",
            r"covalo[^\"']{0,80}",
            r"search\.covalo[^\"']{0,80}",
            r"baseSearch[^\"']{0,80}",
            r"X-Api-Key[^\"']{0,40}",
            r"apiKey\\u0022:\\u0022([^\\]+)",
            r"\"apiKey\"\s*:\s*\"([^\"]+)\"",
        ]:
            hits = re.findall(pat, html, re.I)
            if hits:
                print("html", pat, hits[:8])

        # exhibitor-directory package for keys
        js = client.get("https://css-components.rxweb-prd.com/packages/exhibitor-directory/latest/index.js").text
        for pat, label in [
            (r"algolia", "algolia_n"),
            (r"applicationID[\"'=: ]{0,5}([A-Z0-9]{8,})", "appid"),
            (r"apiKey[\"'=: ]{0,5}([a-zA-Z0-9]{16,})", "apikey"),
            (r"search\.covalo\.com[^\"'\s]{0,80}", "covalo"),
            (r"exhibitors[_-][a-zA-Z0-9_\-]+", "idx"),
            (r"eventEditionId", "edition_n"),
        ]:
            hits = re.findall(pat, js)
            print(label, len(hits), sorted(set(hits))[:10])

        # try covalo search endpoints commonly used by RX
        candidates = [
            f"https://search.covalo.com/v1/exhibitors?eventEditionId={edition}&size=20&from=0",
            f"https://search.covalo.com/exhibitors?eventEditionId={edition}&size=20&from=0",
            f"https://search.covalo.com/v2/search?eventEditionId={edition}&tenant=exhibitors&size=20",
            f"https://api.reedexpo.com/v1/exhibitors?eventEditionId={edition}",
            f"https://api.reedexpo.com/search/exhibitors?eventEditionId={edition}",
        ]
        for u in candidates:
            try:
                r = client.get(u)
                print("GET", r.status_code, u[:90], r.text[:180].replace("\n", " "))
            except Exception as e:
                print("GET fail", u, e)

        # POST search body variants
        bodies = [
            {"eventEditionId": edition, "size": 20, "from": 0, "tenants": ["exhibitors"]},
            {"eventEditionId": edition, "query": "", "size": 20, "page": 0},
            {"editionId": edition, "q": "", "limit": 20},
        ]
        for base in [
            "https://search.covalo.com/v1/search",
            "https://search.covalo.com/search",
            "https://search.covalo.com/v2/search",
            "https://api.reedexpo.com/v2/search",
        ]:
            for b in bodies:
                try:
                    r = client.post(base, json=b, headers={"Content-Type": "application/json"})
                    print("POST", r.status_code, base, list(b.keys()), r.text[:160].replace("\n", " "))
                except Exception as e:
                    print("POST fail", base, e)

        # Extract config blob from page more carefully
        m = re.search(r"var eventEditionId = \"([^\"]+)\".*?var interfaceLocale = \"([^\"]+)\"", html, re.S)
        print("vars", m.groups() if m else None)
        # find JSON config assigned near exhibitor directory
        for m in re.finditer(r"JSON\.parse\(decodeURIComponent\(\"([\s\S]*?)\"\)\)", html):
            raw = m.group(1)
            try:
                # unescape JS string lightly
                text = bytes(raw, "utf-8").decode("unicode_escape")
            except Exception:
                text = raw.replace("\\x22", '"').replace("\\u002D", "-").replace("\\/", "/")
            if "exhibitor" in text.lower() or "covalo" in text.lower() or "search" in text.lower():
                print("JSONBLOB keys sample", text[:500])
                # find api keys
                keys = re.findall(r'"(?:apiKey|searchApiKey|publicApiKey|appId|applicationId|indexName)"\s*:\s*"([^"]+)"', text, re.I)
                print("keys", keys[:20])
                urls = re.findall(r"https://[^\"\\]+", text)
                print("urls", [u for u in urls if "search" in u or "api" in u][:20])


if __name__ == "__main__":
    parcel_profile()
    wtm_search()
