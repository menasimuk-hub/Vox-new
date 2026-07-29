#!/usr/bin/env python3
from __future__ import annotations

import re

import httpx

UA = {"User-Agent": "Mozilla/5.0 Chrome/124.0.0.0"}


def main() -> None:
    with httpx.Client(timeout=60.0, follow_redirects=True, headers=UA) as client:
        js = client.get("https://css-components.rxweb-prd.com/packages/exhibitor-directory/latest/index.js").text
        # find getIndexName definition
        for m in re.finditer(r"getIndexName\s*\(\s*\)\s*\{", js):
            print("DEF", js[m.start(): m.start()+400])
            print("---")
        for m in re.finditer(r"getIndexName\s*=\s*function", js):
            print("FN", js[m.start(): m.start()+400])
        # also look for IndexName helpers
        for m in re.finditer(r"IndexName\s*\([^)]*\)\s*\{[^}]{0,300}\}", js):
            s = m.group(0)
            if "exhibitor" in s.lower() or "edition" in s.lower() or "algolia" in s.lower():
                print("BLK", s[:350])
        # search for strings concatenating exhibitors with edition
        for m in re.finditer(r".{0,60}exhibitors.{0,60}eventEdition.{0,60}", js, re.I):
            print("JOIN", m.group(0)[:200])
        for m in re.finditer(r".{0,40}`[^`]{0,40}exhibitor[^`]{0,40}`", js, re.I):
            print("TPL", m.group(0)[:160])
        # look near "does not exist" style construction - search "exhibitor_" variants
        for term in ["exhibitor_", "Exhibitor_", "EXHIBITOR_", "company_", "Organisation_", "organizations_"]:
            idxs = [i for i in range(len(js)) if js.startswith(term, i)]
            print(term, "count", len(idxs))
            for i in idxs[:5]:
                print(" ", js[i:i+100].replace("\n", " "))

        # page may pass index via attributes - check flux / load component init
        html = client.get("https://www.wtm.com/london/en-gb/exhibitor-directory.html").text
        decoded = html.replace("\\x22", '"').replace("\\u002D", "-").replace("\\/", "/")
        # Find script that initializes exhibitor directory
        for m in re.finditer(r"exhibitor-directory[\s\S]{0,200}", decoded):
            pass
        # look for data-props or React hydrate
        for pat in [r"data-component[^=]*=\"[^\"]+\"", r"exhibitorDirectory[A-Za-z]*\"\s*:\s*\{[^}]{0,400}\}", r"\"index\"\s*:\s*\"[^\"]+\""]:
            hits = re.findall(pat, decoded)
            print(pat, hits[:10])

        # Reed API with public key from page?
        # Search for Authorization / x-api-key values
        for pat in [r"x-api-key\\x22:\\x22([^\\]+)", r"apiKey\\x22:\\x22([^\\]+)", r"\"x-api-key\"\s*:\s*\"([^\"]+)\""]:
            print(pat, re.findall(pat, html)[:10])

        # Try graphql with algolia as key? unlikely
        # Maybe search endpoint on api.reedexpo.com/v1/public/...
        edition = "eve-002a02a9-489e-4cc7-a054-455c6408ead0"
        for u in [
            f"https://api.reedexpo.com/v1/public/event-editions/{edition}/exhibitors?pageSize=5",
            f"https://api.reedexpo.com/v1/event-editions/{edition}/exhibitors?pageSize=5",
            f"https://api.reedexpo.com/v2/event-editions/{edition}/exhibitors?pageSize=5",
            f"https://api.reedexpo.com/catalogue/v1/event-editions/{edition}/exhibitors?size=5",
            f"https://api.reedexpo.com/v1/search/exhibitors?eventEditionId={edition}&size=5",
        ]:
            for headers in [
                {"Accept": "application/json", "User-Agent": UA["User-Agent"]},
                {"Accept": "application/json", "User-Agent": UA["User-Agent"], "x-api-key": KEY},
                {"Accept": "application/json", "User-Agent": UA["User-Agent"], "X-Api-Key": KEY, "X-Algolia-Application-Id": APP},
            ]:
                r = client.get(u, headers=headers)
                if r.status_code != 401:
                    print(r.status_code, u[:90], list(headers.keys()), r.text[:160].replace("\n", " "))
                    break
            else:
                print("all 401", u[:90])


if __name__ == "__main__":
    main()
