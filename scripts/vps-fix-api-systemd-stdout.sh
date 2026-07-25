#!/usr/bin/env bash
# Fix systemd status=209/STDOUT (API crash-loop after install-service).
# Cause: StandardOutput=append:/tmp/voxbulk-api.log not writable by service User=.
#
# Run ON VPS:
#   cd /www/voxbulk && sudo bash scripts/vps-fix-api-systemd-stdout.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SETUP="$ROOT/scripts/vps-setup-api-systemd.sh"

[[ "$(id -u)" -eq 0 ]] || { echo "Run with sudo"; exit 1; }
[[ -f "$SETUP" ]] || { echo "Missing $SETUP — git pull origin main first"; exit 1; }

echo "[fix] Removing broken /tmp log files that block systemd stdout …"
rm -f /tmp/voxbulk-api.log /tmp/voxbulk-public.log

echo "[fix] Re-installing units with /var/log/voxbulk + LogsDirectory …"
bash "$SETUP"

systemctl reset-failed voxbulk-api.service 2>/dev/null || true
systemctl reset-failed voxbulk-public.service 2>/dev/null || true
systemctl restart voxbulk-api.service

sleep 2
systemctl --no-pager --full status voxbulk-api.service | head -n 20 || true

if curl -sf -H "Host: api.voxbulk.com" http://127.0.0.1:8000/health >/dev/null 2>&1 \
  || curl -sf -H "Host: 127.0.0.1" http://127.0.0.1:8000/health >/dev/null 2>&1; then
  echo "[fix] API /health OK"
  exit 0
fi

echo "[fix] Still unhealthy — journal:"
journalctl -u voxbulk-api -n 40 --no-pager || true
exit 1
