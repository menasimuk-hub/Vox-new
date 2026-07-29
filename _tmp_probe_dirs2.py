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


def probe_parcel() -> None:
    print("=" * 80)
    print("PARCEL")
    url = "https://parcelandpostexpo.com/exhibitor-list"
    with httpx.Client(timeout=45.0, follow_redirects=True, headers=UA) as client:
        html = client.get(url).text
        # sample letter page
        letter = client.get(url + "?azletter=A").text
        print("letter A len", len(letter))
        hrefs = re.findall(r'href=["\']([^"\']+)["\']', letter, re.I)
        interesting = []
        for h in hrefs:
            low = h.lower()
            if any(x in low for x in ("exhibitor", "company", "stand", "profile", "detail", "list/")):
                interesting.append(urljoin(url, h))
        print("interesting", len(set(interesting)))
        for u in sorted(set(interesting))[:40]:
            print(" ", u)
        # look for card/list markup snippets
        for pat in [
            r'class=["\'][^"\']*exhibitor[^"\']*["\']',
            r'data-[a-z-]+=["\'][^"\']+["\']',
            r'/exhibitor[^"\']{0,80}',
        ]:
            hits = re.findall(pat, letter, re.I)
            print(pat, "n", len(hits), "sample", sorted(set(hits))[:15])
        # find company name anchors near stand
        for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', letter, re.I | re.S):
            href, text = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if text and len(text) < 80 and "http" not in text.lower() and "exhibitor" not in href.lower():
                continue
            if href and ("exhibitor" in href.lower() or "company" in href.lower() or "/a/" in href.lower()):
                print("ANCHOR", href[:120], "=>", text[:80])
        # dump a chunk of list body
        idx = letter.lower().find("exhibitor")
        print("BODY_SNIP", letter[max(0, idx): max(0, idx)+800].replace("\n", " ")[:800])

        # check site.js for endpoints
        js = client.get("https://themes.asp.events/parcelandpostexpo2025/includes/javascripts/site.js?v=42").text
        print("site.js len", len(js))
        for pat in [r"https?://[^\"'\s]+", r"/[a-z0-9_/-]*exhibitor[a-z0-9_/-]*", r"ajax|fetch|api"]:
            hits = re.findall(pat, js, re.I)
            print("js", pat, sorted(set(hits))[:20])


def probe_wtm() -> None:
    print("=" * 80)
    print("WTM")
    url = "https://www.wtm.com/london/en-gb/exhibitor-directory.html"
    with httpx.Client(timeout=45.0, follow_redirects=True, headers=UA) as client:
        html = client.get(url).text
        # find show-planning / exhibitor-directory package refs
        pkgs = re.findall(r'https://css-components\.rxweb-prd\.com/packages/[^"\']+', html, re.I)
        print("pkgs", sorted(set(pkgs))[:30])
        # find config JSON in page
        for key in ["showId", "editionId", "eventId", "locale", "language", "searchApi", "graphql", "reedexpo", "exhibitors"]:
            hits = re.findall(rf'.{{0,40}}{key}.{{0,80}}', html, re.I)
            print("ctx", key, hits[:5])
        # try exhibitor-directory package
        for path in [
            "https://css-components.rxweb-prd.com/packages/exhibitor-directory/latest/index.js",
            "https://css-components.rxweb-prd.com/packages/show-planning/latest/index.js",
        ]:
            try:
                js = client.get(path).text
                print(path, "len", len(js), "status ok")
                apis = sorted(set(re.findall(r"https://[^\"'\s]{8,120}", js)))
                apis = [a for a in apis if any(k in a.lower() for k in ("api", "graphql", "reed", "search", "exhibitor"))]
                print("  apis", apis[:30])
                paths = sorted(set(re.findall(r"/[a-zA-Z0-9_./-]{0,40}exhibitor[a-zA-Z0-9_./-]{0,40}", js)))
                print("  paths", paths[:30])
                gq = sorted(set(re.findall(r"query\s+[A-Za-z0-9_]+|mutation\s+[A-Za-z0-9_]+|exhibitors\([^)]{0,80}", js)))
                print("  gqlish", gq[:20])
            except Exception as e:
                print("fail", path, e)

        # Try reedexpo graphql introspect-ish search
        gql = "https://api.reedexpo.com/v2/graphql"
        # common RX search
        payloads = [
            {
                "query": "query { __typename }"
            },
        ]
        for p in payloads:
            try:
                resp = client.post(gql, json=p, headers={**UA, "Content-Type": "application/json", "Accept": "application/json"})
                print("gql typename", resp.status_code, resp.text[:300])
            except Exception as e:
                print("gql fail", e)

        # look for window.__INITIAL or similar
        for m in re.finditer(r"window\.[A-Za-z0-9_$]+\s*=\s*", html):
            start = m.start()
            print("window=", html[start:start+120].replace("\n", " "))
        # data attributes on exhibitor-directory root
        m = re.search(r'id=["\']exhibitor-directory["\'][^>]*>', html, re.I)
        if m:
            print("edir_tag", m.group(0)[:500])
        # nearby script config
        idx = html.find("exhibitor-directory")
        print("edir_ctx", html[max(0, idx-200): idx+600].replace("\n", " ")[:800])


if __name__ == "__main__":
    probe_parcel()
    probe_wtm()
