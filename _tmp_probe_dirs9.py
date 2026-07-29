#!/usr/bin/env python3
from __future__ import annotations

import json
import re

import httpx

UA = {"User-Agent": "Mozilla/5.0 Chrome/124.0.0.0"}
APP = "XD0U5M6Y4R"
KEY = "d5cd7d4ec26134ff4a34d736a7f9ad47"
EVENT = "evt-e8fc988b-193b-4372-a1e3-6b6ebf5b2f59"
EDITION = "eve-002a02a9-489e-4cc7-a054-455c6408ead0"


def main() -> None:
    with httpx.Client(timeout=60.0, follow_redirects=True, headers=UA) as client:
        guesses = [
            f"{EVENT}-index",
            f"{EDITION}-index",
            f"{EVENT}_index",
            f"{EDITION}_index",
            f"{EVENT}-exhibitors",
            f"{EDITION}-exhibitors",
            f"index-{EVENT}",
            f"index-{EDITION}",
        ]
        for name in guesses:
            r = client.post(
                f"https://{APP}-dsn.algolia.net/1/indexes/{name}/query",
                headers={
                    "X-Algolia-Application-Id": APP,
                    "X-Algolia-API-Key": KEY,
                    "Content-Type": "application/json",
                },
                json={"params": "query=&hitsPerPage=3"},
            )
            print(name, r.status_code, end=" ")
            if r.status_code == 200:
                data = r.json()
                print("nbHits", data.get("nbHits"))
                hits = data.get("hits") or []
                if hits:
                    print("keys", list(hits[0].keys())[:40])
                    print(json.dumps(hits[0], ensure_ascii=False)[:1000])
            else:
                print(r.text[:100])

        # Also check event.details.json
        d = client.get("https://www.wtm.com/london/api/v1/event.details.json")
        print("details", d.status_code, d.text[:500])

        # Find more -index templates in JS
        js = client.get("https://css-components.rxweb-prd.com/packages/exhibitor-directory/latest/index.js").text
        for m in re.finditer(r"`\$\{[^}]+\}-index`", js):
            print("TPL", m.group(0), "ctx", js[m.start()-60:m.start()+80])
        for m in re.finditer(r"[\"']\$\{[^}]+\}-index[\"']", js):
            print("TPL2", m.group(0))


if __name__ == "__main__":
    main()
