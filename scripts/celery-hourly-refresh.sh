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

# Worker only — beat stays up (hourly beat restarts can double-fire schedules).
# Rolling stop→start (not pkill) so in-flight WA/billing tasks can finish.
ROLL="$ROOT/scripts/celery-rolling-refresh.sh"
if [[ -f "$ROLL" ]]; then
  chmod +x "$ROLL" 2>/dev/null || true
  if VOX_CELERY_WORKER="$WORKER" VOX_CELERY_SKIP_BEAT=1 bash "$ROLL"; then
    echo "$LOG_PREFIX rolling refresh $WORKER OK"
    exit 0
  fi
  echo "$LOG_PREFIX rolling refresh failed — falling back to supervisor restart" >&2
fi

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

if _restart "$WORKER"; then
  sleep 2
  if command -v supervisorctl >/dev/null 2>&1; then
    supervisorctl status "$WORKER" 2>/dev/null || sudo -n supervisorctl status "$WORKER" 2>/dev/null || true
  fi
  exit 0
fi
exit 1
