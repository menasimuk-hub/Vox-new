#!/usr/bin/env bash
# Graceful Celery refresh: SIGTERM worker, wait for in-flight tasks (stopwaitsecs), then start.
# Never pkill celery. Used by ./vox.sh restart and hourly refresh.
#
#   cd /www/voxbulk && bash scripts/celery-rolling-refresh.sh
#   VOX_CELERY_SKIP_BEAT=1 bash scripts/celery-rolling-refresh.sh   # worker only
set -euo pipefail

WORKER="${VOX_CELERY_WORKER:-voxbulk-celery}"
BEAT="${VOX_CELERY_BEAT:-voxbulk-celery-beat}"
SKIP_BEAT="${VOX_CELERY_SKIP_BEAT:-0}"
LOG_PREFIX="[celery-rolling $(date -u +%Y-%m-%dT%H:%M:%SZ)]"

_sup() {
  if command -v supervisorctl >/dev/null 2>&1; then
    if supervisorctl "$@" >/dev/null 2>&1; then
      supervisorctl "$@"
      return $?
    fi
    if command -v sudo >/dev/null 2>&1; then
      sudo -n supervisorctl "$@" 2>/dev/null || sudo supervisorctl "$@"
      return $?
    fi
  fi
  return 1
}

_status() {
  supervisorctl status "$1" 2>/dev/null || sudo -n supervisorctl status "$1" 2>/dev/null || true
}

roll_program() {
  local prog="$1"
  echo "$LOG_PREFIX stop $prog (waits stopwaitsecs for in-flight tasks)"
  if ! _sup stop "$prog"; then
    echo "$LOG_PREFIX FAILED stop $prog" >&2
    return 1
  fi
  echo "$LOG_PREFIX start $prog"
  if ! _sup start "$prog"; then
    echo "$LOG_PREFIX FAILED start $prog — try: sudo supervisorctl start $prog" >&2
    return 1
  fi
  echo "$LOG_PREFIX $prog refreshed"
  _status "$prog"
  return 0
}

if ! command -v supervisorctl >/dev/null 2>&1; then
  echo "$LOG_PREFIX supervisorctl not found — sudo bash scripts/vps-setup-celery.sh" >&2
  exit 1
fi

ok=0
if _status "$WORKER" | grep -q .; then
  if roll_program "$WORKER"; then
    ok=1
  fi
else
  echo "$LOG_PREFIX $WORKER not in supervisor — sudo bash scripts/vps-setup-celery.sh" >&2
fi

if [[ "$SKIP_BEAT" != "1" ]]; then
  if _status "$BEAT" | grep -q .; then
    roll_program "$BEAT" || true
  fi
fi

sleep 2
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CELERY_BIN="$ROOT/voxbulk-api/.venv/bin/celery"
if [[ -x "$CELERY_BIN" ]]; then
  if (cd "$ROOT/voxbulk-api" && "$CELERY_BIN" -A app.workers.celery_app:celery_app inspect ping >/dev/null 2>&1); then
    echo "$LOG_PREFIX worker ping OK"
  else
    echo "$LOG_PREFIX worker ping failed — tail /tmp/voxbulk-celery.err.log" >&2
  fi
fi

[[ "$ok" -eq 1 ]]
