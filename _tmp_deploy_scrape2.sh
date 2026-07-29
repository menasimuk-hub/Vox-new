#!/bin/bash
cd /www/voxbulk || exit 1
git pull origin main
# Prefer reload of systemd API; fall back to vox.sh
if sudo -n systemctl reload voxbulk-api 2>/dev/null; then
  echo reloaded_systemd
elif sudo -n systemctl restart voxbulk-api 2>/dev/null; then
  echo restarted_systemd
else
  ./vox.sh stop || true
  sleep 2
  ./vox.sh start || true
fi
sleep 4
python3 - <<'PY'
import json, urllib.request
req = urllib.request.Request("http://127.0.0.1:8000/health/build", headers={"Host": "api.voxbulk.com"})
with urllib.request.urlopen(req, timeout=15) as r:
    d = json.load(r)
print("health", d.get("git_sha"), d.get("built_at"))
PY
cd /www/voxbulk/voxbulk-api
source .venv/bin/activate
PYTHONPATH=. python -u <<'PY'
from app.services.expo_directory_scraper_service import ExpoDirectoryScraper
for url, n in [
    ("https://parcelandpostexpo.com/exhibitor-list", 30),
    ("https://www.wtm.com/london/en-gb/exhibitor-directory.html", 50),
]:
    r = ExpoDirectoryScraper.scrape(url, follow_websites=True, max_stands=n)
    print(url, "->", r.get("provider"), "emails", r.get("emails_found"), "stands", r.get("stands_found"))
PY
