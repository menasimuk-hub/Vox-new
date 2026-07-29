#!/usr/bin/env python3
from __future__ import annotations

import json
import re

import httpx

UA = {"User-Agent": "Mozilla/5.0 Chrome/124.0.0.0"}
APP = "XD0U5M6Y4R"
KEY = "d5cd7d4ec26134ff4a34d736a7f9ad47"
EDITION = "eve-002a02a9-489e-4cc7-a054-455c6408ead0"


def main() -> None:
    with httpx.Client(timeout=90.0, follow_redirects=True, headers=UA) as client:
        html = client.get("https://www.wtm.com/london/en-gb/exhibitor-directory.html").text
        decoded = html.replace("\\x22", '"').replace("\\u002D", "-").replace("\\/", "/")
        # Find load-flux / component mount config
        idx = decoded.find("exhibitor-directory/latest")
        print("pkg pos", idx)
        print(decoded[max(0, idx - 800): idx + 800])
        print("====")
        # Find all script inline with eventEditionId assignment block
        m = re.search(r"var eventEditionId = \"([^\"]+)\"[\s\S]{0,2500}?</script>", html)
        if m:
            block = m.group(0)
            print("BLOCK", block[:2000])
            print("====")
            # unescape
            bdec = block.replace("\\x22", '"').replace("\\u002D", "-").replace("\\/", "/")
            for pat in [r"indexName[^\n]{0,120}", r"algolia[^\n]{0,200}", r"search[A-Za-z]*\s*=\s*[^\n]{0,120}"]:
                print(pat, re.findall(pat, bdec)[:10])

        js = client.get("https://css-components.rxweb-prd.com/packages/exhibitor-directory/latest/index.js").text
        # Extract function bodies containing getIndexName text
        pos = js.find("getIndexName")
        print("first getIndexName", pos)
        while pos != -1 and pos < len(js):
            print(js[max(0, pos - 80): pos + 250].replace("\n", " "))
            print("---")
            pos = js.find("getIndexName", pos + 1)
            if pos > 2000000:
                break
            # limit prints
            if js.find("getIndexName", pos + 1) - pos > 0 and pos > 500000:
                # print a few more then stop
                if pos > 600000:
                    break

        # Try Algolia browse with facetFilters eventEditionId on random common indexes
        # Use analytics? no
        # Try search API with index name from RX conventions found online / guessed
        # Often: `{tenant}_{eventEditionId}` with tenant Exhibitors capitalized
        for name in [
            f"Exhibitors_{EDITION}",
            f"Products_{EDITION}",
            f"exhibitors{EDITION}",
            f"Exhibitors{EDITION}",
            f"exh-{EDITION}",
            f"directory_{EDITION}",
            f"Catalogue_{EDITION}",
            f"Organisations_{EDITION}",
            f"Organizations_{EDITION}",
            f"Companies_{EDITION}",
            f"Participants_{EDITION}",
            f"Standholders_{EDITION}",
            f"exhibitors_evt-e8fc988b-193b-4372-a1e3-6b6ebf5b2f59",
            f"Exhibitors_evt-e8fc988b-193b-4372-a1e3-6b6ebf5b2f59",
        ]:
            r = client.post(
                f"https://{APP}-dsn.algolia.net/1/indexes/{name}/query",
                headers={
                    "X-Algolia-Application-Id": APP,
                    "X-Algolia-API-Key": KEY,
                    "Content-Type": "application/json",
                },
                json={"params": "query=&hitsPerPage=1"},
            )
            print(name, r.status_code, (r.json().get("nbHits") if r.status_code == 200 else r.text[:80]))

        # Inspect load-flux package for index naming
        flux = client.get("https://css-components.rxweb-prd.com/packages/load-flux/latest/index.js").text
        for m in re.finditer(r".{0,40}indexName.{0,100}", flux):
            s = m.group(0)
            if "exhibitor" in s.lower() or "edition" in s.lower() or "algolia" in s.lower():
                print("FLUX", s[:180])
        for m in re.finditer(r"exhibitors_[\$`'\"][^,;]{0,80}", flux, re.I):
            print("FLUX2", m.group(0)[:160])


if __name__ == "__main__":
    main()
