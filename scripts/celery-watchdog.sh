#!/usr/bin/env bash
# Celery watchdog — check worker/beat health, auto-restart via Supervisor, email admin.
#
# Install (VPS, once):
#   sudo bash scripts/vps-setup-celery.sh   # also installs cron
# Or manually:
#   */5 * * * * /www/voxbulk/scripts/celery-watchdog.sh >> /tmp/voxbulk-celery-watchdog.log 2>&1
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$ROOT/voxbulk-api"
PY="$API_DIR/.venv/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "[celery-watchdog] missing venv python: $PY" >&2
  exit 1
fi

cd "$API_DIR"
export PYTHONPATH="$API_DIR"
exec "$PY" - <<'PY'
from app.services.celery_ops_service import watchdog_tick
import json

result = watchdog_tick(auto_restart=True, send_email=True)
status = result.get("status") or {}
print(json.dumps({
    "ok": status.get("ok"),
    "checked_at": status.get("checked_at"),
    "issues": status.get("issues"),
    "restart_ok": (result.get("restart") or {}).get("ok"),
    "alert": result.get("alert"),
}, default=str))
raise SystemExit(0 if status.get("ok") else 1)
PY
