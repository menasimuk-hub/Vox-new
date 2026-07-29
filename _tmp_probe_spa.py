from app.services.expo_directory_scraper_service import ExpoDirectoryScraper

url = "https://takeawayexpo.co.uk/exhibitors"
print("probing", url)
try:
    result = ExpoDirectoryScraper.scrape(url, follow_websites=False, max_stands=500)
    print("provider", result.get("provider"))
    print("stands", result.get("stands_found"))
    print("with_email", result.get("stands_with_email"))
    print("emails", result.get("emails_found"))
    print("warning", (result.get("warning") or "")[:200])
    contacts = result.get("contacts") or []
    print("sample", [c.get("email") for c in contacts[:5]])
except Exception as e:
    print("ERROR", type(e).__name__, e)
