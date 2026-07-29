#!/usr/bin/env python3
"""Discover exhibitor-directory URLs for UK exhibitions from Book1.xlsx."""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

import httpx

# Direct rows from Book1 (already have directories)
KNOWN = [
    ("IFE", "https://www.ife.co.uk/exhibitor-list"),
    ("HRC", "https://www.hrc.co.uk/hrc-2026-exhibitor-list"),
    ("IFE Manufacturing", "https://www.ifemanufacturing.co.uk/exhibitor-list"),
    ("London Book Fair", "https://www.londonbookfair.co.uk/en-gb/exhibitor-directory.html"),
    ("Makers Central", "https://www.makerscentral.co.uk/exhibitor-list/"),
    ("APEA Live", "https://www.apealive.co.uk/2026/exhibition/exhibitor-list/"),
    ("BIG Futures Show", "https://bigfuturesshow.org.uk/exhibitordirectory/"),
    ("UK Games Expo", "https://www.ukgamesexpo.co.uk/whats-on/show/exhibitors/"),
    ("The Pub Show", "https://www.thepubshow.co.uk/exhibitor-list"),
    ("Hospitality Tech360", "https://www.hospitalitytech360.co.uk/exhibitor-list"),
]

# Shows named under organisers without a directory URL in the sheet
FIND = [
    ("Spring Fair", "https://www.springfair.com"),
    ("Bett", "https://www.bettshow.com"),
    ("Autumn Fair", "https://www.autumnfair.com"),
    ("Multimodal", "https://www.multimodal.org.uk"),
    ("Digital Construction Week", "https://www.digitalconstructionweek.com"),
    ("World Travel Market", "https://www.wtm.com/london"),
    ("InstallerSHOW", "https://www.installershow.com"),
    ("Safety & Health Expo", "https://www.safetyhealthandwellbeingworld.com"),
    ("Advanced Engineering UK", "https://www.advancedengineeringuk.com"),
    ("Packaging Innovations", "https://www.packaginginnovations-event.com"),
    ("UK Construction Week", "https://www.ukconstructionweek.com"),
    ("Clerkenwell Design Week", "https://www.clerkenwelldesignweek.com"),
    ("LAMMA", "https://www.lammashow.com"),
    ("CropTec", "https://www.croptecshow.com"),
    ("National Convenience Show", "https://www.convenience.org.uk"),
    ("The Forecourt Show", "https://www.forecourtshow.com"),
    ("GEO Business", "https://www.geobusinessshow.com"),
    ("Emergency Services Show", "https://www.emergencyuk.com"),
    ("Commercial Vehicle Show", "https://www.cvshow.com"),
    ("Road Transport Expo", "https://www.roadtransportexpo.co.uk"),
    ("Accountex Summit North", "https://www.accountex.co.uk"),
    ("Natural & Organic Products Expo", "https://www.naturalproducts.co.uk"),
    ("Southampton International Boat Show", "https://www.southamptonboatshow.com"),
    ("CHEMUK", "https://www.chemicalukexpo.com"),
    ("Independent Hotel Show", "https://www.independenthotelshow.co.uk"),
]

UA = {
    "User-Agent": "Mozilla/5.0 (compatible; VoxBulkExpoFinder/1.0)",
    "Accept": "text/html,application/xhtml+xml",
}

CANDIDATE_PATHS = [
    "/exhibitor-list",
    "/exhibitor-list/",
    "/exhibitors",
    "/exhibitors/",
    "/exhibitor-directory",
    "/exhibitor-directory.html",
    "/en-gb/exhibitor-directory.html",
    "/en-gb/exhibitor-list",
    "/whats-on/exhibitors",
    "/exhibition/exhibitor-list",
    "/2026/exhibition/exhibitor-list/",
    "/2025/exhibition/exhibitor-list/",
    "/exhibitordirectory",
    "/exhibitordirectory/",
    "/visit/exhibitors",
    "/visitors/exhibitor-list",
    "/floorplan",
]


def score_url(url: str, html: str) -> int:
    low = (html or "").lower()
    u = url.lower()
    score = 0
    if any(t in u for t in ("exhibitor-list", "exhibitor-directory", "exhibitors", "exhibitordirectory")):
        score += 5
    if "exhibitor" in low:
        score += 2
    if any(t in low for t in ("azletter", "m-exhibitors-list", "algoliaconfig", "easyfairs", "stand")):
        score += 4
    if "mailto:" in low or "@" in low:
        score += 1
    if len(html or "") > 20000:
        score += 1
    if any(t in low for t in ("404", "not found", "page not found")) and len(html or "") < 5000:
        score -= 10
    return score


def discover(name: str, home: str) -> dict:
    out = {"name": name, "home": home, "best": None, "candidates": []}
    try:
        with httpx.Client(timeout=25.0, follow_redirects=True, headers=UA) as client:
            home_r = client.get(home)
            home_html = home_r.text or ""
            base = str(home_r.url)
            parsed = urlparse(base)
            origin = f"{parsed.scheme}://{parsed.netloc}"

            # links from homepage mentioning exhibitor
            hrefs = re.findall(r'href=["\']([^"\']+)["\']', home_html, re.I)
            urls = []
            for h in hrefs:
                full = urljoin(base, h).split("#")[0].split("?")[0]
                if urlparse(full).netloc.lower() != parsed.netloc.lower():
                    continue
                if "exhibitor" in full.lower() or "stand" in full.lower():
                    urls.append(full)
            for path in CANDIDATE_PATHS:
                urls.append(urljoin(origin + "/", path.lstrip("/")))
            # dedupe
            seen = set()
            uniq = []
            for u in urls:
                if u not in seen:
                    seen.add(u)
                    uniq.append(u)

            best = None
            best_score = -99
            for u in uniq[:40]:
                try:
                    r = client.get(u)
                    if r.status_code >= 400:
                        continue
                    sc = score_url(str(r.url), r.text or "")
                    item = {"url": str(r.url), "status": r.status_code, "score": sc, "len": len(r.text or "")}
                    out["candidates"].append(item)
                    if sc > best_score:
                        best_score = sc
                        best = item
                except Exception:
                    continue
            out["best"] = best
    except Exception as e:
        out["error"] = str(e)
    return out


def main():
    results = []
    for name, home in FIND:
        print("FIND", name, home)
        d = discover(name, home)
        results.append(d)
        print("  BEST", d.get("best"))
    print(json.dumps({"known": KNOWN, "found": results}, indent=2)[:8000])
    with open("/tmp/exhibition_dirs.json", "w", encoding="utf-8") as f:
        json.dump({"known": KNOWN, "found": results}, f, indent=2)


if __name__ == "__main__":
    main()
