#!/usr/bin/env python3
from app.services.expo_directory_scraper_service import ExpoDirectoryScraper

r = ExpoDirectoryScraper.scrape(
    "https://www.ife.co.uk/exhibitor-list",
    follow_websites=True,
    max_stands=6,
)
print(
    "provider", r.get("provider"),
    "stands", r.get("stands_found"),
    "emails", r.get("emails_found"),
)
for c in (r.get("contacts") or [])[:5]:
    print(" ", c.get("email"), "|", (c.get("company_name") or "")[:40])
