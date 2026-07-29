#!/bin/bash
set -e
cd /www/voxbulk
./vox.sh stop || true
sleep 2
./vox.sh start
sleep 5
echo "=== HEALTH ==="
curl -sS -H 'Host: api.voxbulk.com' http://127.0.0.1:8000/health/build | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("git_sha"), d.get("built_at"))'
echo "=== CODE ==="
grep -n "VOX_SCRAPE_USE_CELERY" voxbulk-api/app/services/ai_team_service.py | head -3
echo "=== ADMIN ==="
ls -1 /www/wwwroot/admin.voxbulk.com/assets/ApifyOutreach*.js | tail -1
echo "=== INLINE SCRAPE TEST (wait=False default path) ==="
cd /www/voxbulk/voxbulk-api
source .venv/bin/activate
PYTHONPATH=. python -u <<'PY'
from app.services.ai_team_service import AiTeamService
from app.core.database import get_sessionmaker
db = get_sessionmaker()()
out = AiTeamService.start_directory_scrape(
    db,
    expo_url="https://takeawayexpo.co.uk/exhibitors",
    follow_websites=False,
    wait=False,
    max_stands=500,
)
print("provider", out.get("provider") or (out.get("run") or {}).get("provider"))
print("emails", out.get("emails_found") or (out.get("run") or {}).get("emails_found") or (out.get("run") or {}).get("item_count"))
print("queued_via", out.get("queued_via"))
print("message", out.get("message"))
print("status", (out.get("run") or {}).get("status"))
db.close()
PY
