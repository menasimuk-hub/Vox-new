#!/usr/bin/env python3
from app.services.expo_directory_scraper_service import ExpoDirectoryScraper

URLS = [
    "https://parcelandpostexpo.com/exhibitor-list",
    "https://www.wtm.com/london/en-gb/exhibitor-directory.html",
]

for url in URLS:
    print("=" * 80)
    print(url)
    # Cap for speed in verify; production uses up to 1000
    max_stands = 40 if "parcel" in url else 80
    result = ExpoDirectoryScraper.scrape(url, follow_websites=True, max_stands=max_stands)
    print(
        "provider", result.get("provider"),
        "stands", result.get("stands_found"),
        "with_email", result.get("stands_with_email"),
        "emails", result.get("emails_found"),
        "warn", (result.get("warning") or "")[:120],
    )
    contacts = result.get("contacts") or []
    for c in contacts[:5]:
        print(" ", c.get("email"), "|", (c.get("company_name") or "")[:40])
