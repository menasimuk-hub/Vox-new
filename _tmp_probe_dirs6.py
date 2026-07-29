#!/usr/bin/env python3
from __future__ import annotations

import json
import re

import httpx

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"}
APP = "XD0U5M6Y4R"
KEY = "d5cd7d4ec26134ff4a34d736a7f9ad47"
EDITION = "eve-002a02a9-489e-4cc7-a054-455c6408ead0"


def main() -> None:
    with httpx.Client(timeout=60.0, follow_redirects=True, headers=UA) as client:
        html = client.get("https://www.wtm.com/london/en-gb/exhibitor-directory.html").text
        decoded = (
            html.replace("\\x22", '"')
            .replace("\\u002D", "-")
            .replace("\\u0022", '"')
            .replace("\\/", "/")
            .replace("\\x27", "'")
        )
        # Find large config objects mentioning algolia/exhibitors
        for key in ["algoliaConfig", "searchConfig", "exhibitorDirectory", "directoryConfig", "fluxConfig"]:
            idx = decoded.find(key)
            print(key, "pos", idx)
            if idx >= 0:
                print(decoded[idx: idx + 500])
                print("---")

        # Find all strings containing eve-002a
        for m in re.finditer(r".{0,40}eve-002a02a9-489e-4cc7-a054-455c6408ead0.{0,80}", decoded):
            print("ED", m.group(0)[:160])

        # Search JS for how index is built
        js = client.get("https://css-components.rxweb-prd.com/packages/exhibitor-directory/latest/index.js").text
        for pat in [
            r"exhibitors_\$\{[^}]+\}",
            r"exhibitors_\"\+[^\"]{0,40}",
            r"[\"']exhibitors_[\"']\s*\+",
            r"indexName\s*[:=]\s*[`'\"][^`'\"]+[`'\"]",
            r"getIndexName\([^)]{0,40}\)",
            r"buildIndex[^,]{0,80}",
            r"exhibitorIndex[^,]{0,80}",
            r"tenantIndex[^,]{0,80}",
            r"[\"']exhibitors_[a-zA-Z0-9_\-]+[\"']",
        ]:
            hits = re.findall(pat, js)
            if hits:
                print("PAT", pat, hits[:20])

        # Context around 'exhibitors_' in js
        for m in re.finditer(r"exhibitors_", js):
            print("CTX", js[m.start()-30:m.start()+80].replace("\n", " "))
            if m.start() > 500000:
                break

        # Try multi-query / search endpoints with filters
        guesses = [
            f"Exhibitors_{EDITION}",
            f"exhibitors_{EDITION.replace('-', '')}",
            f"prod_Exhibitors_{EDITION}",
            f"Exhibitors-{EDITION}",
            f"exh_{EDITION}",
            f"EventExhibitors_{EDITION}",
            f"rx_exhibitors_{EDITION}",
            "Exhibitors",
            "exhibitors_prod",
            "prod_exhibitors",
            f"{EDITION}",
        ]
        # Also pull possible names from page
        guesses += re.findall(r"[A-Za-z0-9_\-]{5,80}exhibitor[A-Za-z0-9_\-]{0,40}", decoded, re.I)[:50]
        guesses = list(dict.fromkeys(guesses))
        print("trying", len(guesses))
        for name in guesses:
            endpoint = f"https://{APP}-dsn.algolia.net/1/indexes/{name}/query"
            rr = client.post(
                endpoint,
                headers={
                    "X-Algolia-Application-Id": APP,
                    "X-Algolia-API-Key": KEY,
                    "Content-Type": "application/json",
                },
                json={"params": "query=&hitsPerPage=1"},
            )
            if rr.status_code == 200:
                data = rr.json()
                print("OK", name, "nbHits", data.get("nbHits"))
                hits = data.get("hits") or []
                if hits:
                    print("keys", list(hits[0].keys())[:30])
                    print(json.dumps(hits[0], ensure_ascii=False)[:700])
                break
            if rr.status_code not in (404, 403):
                print(name, rr.status_code, rr.text[:100])

        # Try search with facet filter on a known index from package
        # Multi index query
        r2 = client.post(
            f"https://{APP}-dsn.algolia.net/1/indexes/*/queries",
            headers={
                "X-Algolia-Application-Id": APP,
                "X-Algolia-API-Key": KEY,
                "Content-Type": "application/json",
            },
            json={
                "requests": [
                    {"indexName": g, "params": "query=&hitsPerPage=1"}
                    for g in [
                        f"exhibitors_{EDITION}",
                        f"Exhibitors_{EDITION}",
                        "exhibitors",
                        "Exhibitors",
                    ]
                ]
            },
        )
        print("multi", r2.status_code, r2.text[:400])


if __name__ == "__main__":
    main()
