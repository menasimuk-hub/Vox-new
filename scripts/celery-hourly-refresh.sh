#!/usr/bin/env bash
# Soft-reload Celery worker every hour so new task modules load after deploys
# even when deploy-time supervisor restart failed (sudo password / NOPASSWD gap).
#
# Installed by: sudo bash scripts/vps-setup-celery.sh
# Cron: 5 * * * * /www/voxbulk/scripts/celery-hourly-refresh.sh >> /tmp/voxbulk-celery-hourly.log 2>&1
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKER="voxbulk-celery"
LOG_PREFIX="[celery-hourly $(date -u +%Y-%m-%dT%H:%M:%SZ)]"

_restart() {
  local prog="$1"
  if command -v supervisorctl >/dev/null 2>&1; then
    if supervisorctl restart "$prog" >/dev/null 2>&1; then
      echo "$LOG_PREFIX restarted $prog (no sudo)"
      return 0
    fi
    if sudo -n supervisorctl restart "$prog" >/dev/null 2>&1; then
      echo "$LOG_PREFIX restarted $prog (sudo -n)"
      return 0
    fi
    if sudo supervisorctl restart "$prog" >/dev/null 2>&1; then
      echo "$LOG_PREFIX restarted $prog (sudo)"
      return 0
    fi
  fi
  echo "$LOG_PREFIX FAILED to restart $prog" >&2
  return 1
}

# Worker only — beat stays up (hourly beat restarts can double-fire schedules).
if _restart "$WORKER"; then
  sleep 2
  if command -v supervisorctl >/dev/null 2>&1; then
    supervisorctl status "$WORKER" 2>/dev/null || sudo -n supervisorctl status "$WORKER" 2>/dev/null || true
  fi
  exit 0
fi
exit 1
