#!/usr/bin/env bash
set -euo pipefail
cd /www/voxbulk
MAINPID=$(systemctl show -p MainPID --value voxbulk-api 2>/dev/null || true)
if [[ -n "${MAINPID:-}" && "$MAINPID" != "0" ]]; then
  kill -HUP "$MAINPID" || true
  echo "HUP sent to $MAINPID"
fi
sleep 5
curl -s -H 'Host: api.voxbulk.com' http://127.0.0.1:8000/health/build > /tmp/vox_health_build.json
python3 - <<'PY'
import json
from pathlib import Path
d = json.loads(Path("/tmp/vox_health_build.json").read_text())
print("health_sha", d.get("git_sha"), d.get("git_sha_full"))
print("app_version", d.get("app_version"))
print("pid", d.get("pid"))
text = Path("voxbulk-api/app/services/expo_directory_scraper_service.py").read_text()
print("on_disk_montgomery", "montgomerygroup" in text)
print("on_disk_openRemoteModal", "openRemoteModal" in text)
PY
git rev-parse --short HEAD
