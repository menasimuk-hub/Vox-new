#!/usr/bin/env bash
# VOXBULK VPS — start / stop / reload API A+B; public/admin/dashboard are static wwwroot
# Prefers systemd units (voxbulk-api / voxbulk-api-b) when installed; falls back to nohup.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$ROOT/voxbulk-api"
PUBLIC_DIR="$ROOT/voxbulk.com/frontend"
DASH_DIR="$ROOT/dashboard.voxbulk.com/dashboard-web"
API_LOG="/tmp/voxbulk-api.log"
PUBLIC_LOG="/tmp/voxbulk-public.log"
DASH_LOG="/tmp/voxbulk-dashboard.log"
SETUP_SYSTEMD="$ROOT/scripts/vps-setup-api-systemd.sh"
API_UNIT_NAME="voxbulk-api"
API_B_UNIT_NAME="voxbulk-api-b"
PUBLIC_UNIT_NAME="voxbulk-public"
PUBLIC_WWWROOT="${VOX_PUBLIC_DIST:-/www/wwwroot/voxbulk.com}"

api_supports_graceful_reload() {
  # gunicorn unit has ExecReload=HUP — keeps the listen socket up during deploy
  [[ -f "/etc/systemd/system/${API_UNIT_NAME}.service" ]] \
    && grep -q 'ExecReload=' "/etc/systemd/system/${API_UNIT_NAME}.service" 2>/dev/null
}

# ── systemd helpers ──────────────────────────────────────────────────────────

_sys() {
  # Mutating ops need root/sudo; status/is-active are readable without sudo and
  # may return non-zero when the unit is inactive (that is not a permission error).
  case "${1:-}" in
    start|stop|restart|enable|disable|daemon-reload|kill|reload|reload-or-restart|try-reload-or-restart)
      if [[ "$(id -u)" -eq 0 ]]; then
        systemctl "$@"
        return $?
      fi
      if command -v sudo >/dev/null 2>&1; then
        if sudo -n systemctl "$@" 2>/dev/null; then
          return 0
        fi
        sudo systemctl "$@"
        return $?
      fi
      systemctl "$@"
      return $?
      ;;
    *)
      systemctl "$@"
      return $?
      ;;
  esac
}

api_systemd_installed() {
  [[ -f "/etc/systemd/system/${API_UNIT_NAME}.service" ]] \
    || _sys cat "${API_UNIT_NAME}.service" >/dev/null 2>&1
}

api_b_systemd_installed() {
  [[ -f "/etc/systemd/system/${API_B_UNIT_NAME}.service" ]] \
    || _sys cat "${API_B_UNIT_NAME}.service" >/dev/null 2>&1
}

public_systemd_installed() {
  [[ -f "/etc/systemd/system/${PUBLIC_UNIT_NAME}.service" ]] \
    || _sys cat "${PUBLIC_UNIT_NAME}.service" >/dev/null 2>&1
}

# ── process stop (nohup / orphans) ───────────────────────────────────────────

stop_api_processes() {
  # Full stop only (vox.sh stop). Never call this during deploy/reload — it takes both ports down.
  pkill -f "uvicorn.*main:app" 2>/dev/null || true
  pkill -f "python -m uvicorn.*main:app" 2>/dev/null || true
  pkill -f "gunicorn.*main:app" 2>/dev/null || true
  sleep 1
  if command -v fuser >/dev/null 2>&1; then
    fuser -k 8000/tcp 2>/dev/null || true
    fuser -k 8001/tcp 2>/dev/null || true
  fi
  sleep 1
}

stop_public_processes() {
  pkill -f "vite preview.*5173" 2>/dev/null || true
  pkill -f "npm run preview.*5173" 2>/dev/null || true
}

stop_dashboard() {
  pkill -f "vite preview.*5175" 2>/dev/null || true
  pkill -f "npm run preview.*5175" 2>/dev/null || true
}

stop_api() {
  if api_systemd_installed; then
    _sys stop "${API_UNIT_NAME}.service" 2>/dev/null || true
  fi
  if api_b_systemd_installed; then
    _sys stop "${API_B_UNIT_NAME}.service" 2>/dev/null || true
  fi
  stop_api_processes
}

stop_public() {
  if public_systemd_installed; then
    _sys stop "${PUBLIC_UNIT_NAME}.service" 2>/dev/null || true
    stop_public_processes
  else
    stop_public_processes
  fi
}

_env_val() {
  local key="$1"
  grep -E "^${key}=" "$API_DIR/.env" 2>/dev/null | tail -n1 | cut -d= -f2- | tr -d '\r' | sed 's/^["'\'']//;s/["'\'']$//' || true
}

is_production_env() {
  local e
  e="$(_env_val ENV)"
  [[ "$e" == "production" || "$e" == "prod" ]]
}

skip_public_preview() {
  if [[ "${VOX_PUBLIC_PREVIEW:-0}" == "1" ]]; then
    return 1
  fi
  if [[ "${VOX_SKIP_PUBLIC_RESTART:-0}" == "1" ]]; then
    return 0
  fi
  [[ -f "$PUBLIC_WWWROOT/index.html" ]] && return 0
  is_production_env && return 0
  return 1
}

skip_dashboard_preview() {
  if [[ "${VOX_DASHBOARD_PREVIEW:-0}" == "1" ]]; then
    return 1
  fi
  if [[ "${VOX_SKIP_DASHBOARD_PREVIEW:-0}" == "1" ]]; then
    return 0
  fi
  is_production_env && return 0
  [[ -d /www/wwwroot/dashboard.voxbulk.com ]] && return 0
  return 1
}

_supervisorctl() {
  if command -v supervisorctl >/dev/null 2>&1; then
    if supervisorctl "$@" >/dev/null 2>&1; then
      supervisorctl "$@"
      return $?
    fi
    if command -v sudo >/dev/null 2>&1; then
      sudo -n supervisorctl "$@" 2>/dev/null && return 0
    fi
  fi
  return 1
}

# ── Celery (Supervisor) ──────────────────────────────────────────────────────

celery_supervisor_name() {
  if _supervisorctl status voxbulk-celery >/dev/null 2>&1; then
    echo "voxbulk-celery"
    return 0
  fi
  if _supervisorctl status retover-celery >/dev/null 2>&1; then
    echo "retover-celery"
    return 0
  fi
  return 1
}

celery_beat_supervisor_name() {
  if _supervisorctl status voxbulk-celery-beat >/dev/null 2>&1; then
    echo "voxbulk-celery-beat"
    return 0
  fi
  return 1
}

restart_celery() {
  # Drop stale beat schedule before rolling start so new beat_schedule entries load.
  if [[ -f "$ROOT/voxbulk-api/celerybeat-schedule.db" ]]; then
    rm -f "$ROOT/voxbulk-api/celerybeat-schedule.db" "$ROOT/voxbulk-api/celerybeat-schedule.db-shm" "$ROOT/voxbulk-api/celerybeat-schedule.db-wal" 2>/dev/null || true
    echo "Removed stale celerybeat-schedule.db (beat will recreate)"
  fi
  # Rolling stop→start so in-flight tasks can finish (Supervisor stopwaitsecs). Never pkill celery.
  local roller="$ROOT/scripts/celery-rolling-refresh.sh"
  if [[ -x "$roller" ]] || [[ -f "$roller" ]]; then
    chmod +x "$roller" 2>/dev/null || true
    if bash "$roller"; then
      echo "Celery rolling refresh OK"
    else
      echo "WARNING: Celery rolling refresh failed — sudo bash scripts/celery-rolling-refresh.sh"
    fi
  else
    echo "WARNING: missing $roller — sudo bash scripts/vps-setup-celery.sh"
  fi
}

status_celery() {
  echo ""
  echo "=== Celery (WA voice notes, async jobs, billing beat) ==="
  local name beat ok=0
  if name="$(celery_supervisor_name)"; then
    _supervisorctl status "$name" || true
    if _supervisorctl status "$name" 2>/dev/null | grep -q RUNNING; then
      ok=1
    fi
  elif pgrep -af "celery.*worker" >/dev/null 2>&1; then
    echo "supervisorctl cannot see voxbulk-celery (try sudo) — worker process is running"
  else
    echo "voxbulk-celery not configured — run: sudo bash scripts/vps-setup-celery.sh"
  fi
  if beat="$(celery_beat_supervisor_name)"; then
    _supervisorctl status "$beat" || true
    if _supervisorctl status "$beat" 2>/dev/null | grep -q RUNNING; then
      ok=1
    fi
  elif pgrep -af "celery.*beat" >/dev/null 2>&1; then
    echo "supervisorctl cannot see voxbulk-celery-beat (try sudo) — beat process is running"
  else
    echo "voxbulk-celery-beat not configured — run: sudo bash scripts/vps-setup-celery.sh"
  fi
  if pgrep -af "celery.*worker" >/dev/null 2>&1; then
    pgrep -af "celery.*worker" | head -3
    ok=1
  else
    echo "no celery worker process"
  fi
  if pgrep -af "celery.*beat" >/dev/null 2>&1; then
    pgrep -af "celery.*beat" | head -2
    ok=1
  else
    echo "no celery beat process"
  fi
  local redis_url
  redis_url="$(_env_val CELERY_BROKER_URL)"
  [[ -z "$redis_url" ]] && redis_url="$(_env_val REDIS_URL)"
  if [[ -n "$redis_url" ]] && command -v redis-cli >/dev/null 2>&1 && redis-cli -u "$redis_url" ping >/dev/null 2>&1; then
    echo "redis: PONG (from .env broker URL)"
  elif command -v redis-cli >/dev/null 2>&1 && redis-cli ping >/dev/null 2>&1; then
    echo "redis: PONG"
  elif pgrep -af "celery.*worker" >/dev/null 2>&1; then
    echo "redis: default redis-cli ping failed (workers are up — broker URL likely has a password; that is OK)"
  else
    echo "redis: not responding"
    ok=0
  fi
  [[ "$ok" -eq 1 ]]
}

wait_for_http() {
  local url="$1"
  local host_header="${2:-}"
  local attempts="${3:-20}"
  local i=0
  while (( i < attempts )); do
    if [[ -n "$host_header" ]]; then
      curl -sf -H "Host: $host_header" "$url" >/dev/null 2>&1 && return 0
    else
      curl -sf "$url" >/dev/null 2>&1 && return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  return 1
}

show_log_tail() {
  local file="$1"
  local label="$2"
  if [[ -f "$file" ]]; then
    echo "--- last lines of $label ($file) ---"
    tail -n 20 "$file" || true
    echo "---"
  fi
}

migrate_api_if_needed() {
  if [[ "${VOX_SKIP_MIGRATE:-0}" == "1" ]]; then
    return 0
  fi
  cd "$API_DIR"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m alembic upgrade head || echo "Warning: alembic upgrade failed — API will retry migrations on boot"
}

start_api_nohup() {
  cd "$API_DIR"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  # setsid + </dev/null fully detaches uvicorn into its own session so it keeps
  # running after the launching shell (e.g. deploy-vps.sh) exits or aborts.
  setsid nohup uvicorn main:app --host 127.0.0.1 --port 8000 --workers "${VOX_UVICORN_WORKERS:-1}" >>"$API_LOG" 2>&1 </dev/null &
  echo "API started via nohup (log: $API_LOG)"
}

start_api() {
  migrate_api_if_needed
  if api_systemd_installed; then
    if _sys is-active --quiet "${API_UNIT_NAME}.service" 2>/dev/null; then
      echo "API A already active via systemd ($API_UNIT_NAME)"
    elif _sys start "${API_UNIT_NAME}.service"; then
      echo "API A started via systemd ($API_UNIT_NAME)"
    else
      echo "Warning: systemctl start $API_UNIT_NAME failed — falling back to nohup"
      start_api_nohup
    fi
  else
    start_api_nohup
  fi
  if api_b_systemd_installed; then
    if _sys is-active --quiet "${API_B_UNIT_NAME}.service" 2>/dev/null; then
      echo "API B already active via systemd ($API_B_UNIT_NAME)"
    elif _sys start "${API_B_UNIT_NAME}.service"; then
      echo "API B started via systemd ($API_B_UNIT_NAME)"
    else
      echo "Warning: systemctl start $API_B_UNIT_NAME failed"
    fi
  fi
}

# Rolling recycle — reload A, wait /health, then reload B. Never both at once.
reload_api() {
  migrate_api_if_needed
  if ! api_systemd_installed; then
    echo "systemd unit not installed — falling back to restart"
    stop_api
    sleep 1
    start_api
    return $?
  fi
  if ! api_supports_graceful_reload; then
    echo "Unit has no ExecReload — run: sudo bash scripts/vps-setup-api-systemd.sh"
    echo "Falling back to sequential systemctl restart"
    _sys restart "${API_UNIT_NAME}.service" || start_api_nohup
    if api_b_systemd_installed; then
      if wait_for_http "http://127.0.0.1:8000/health" "api.voxbulk.com" 30 \
        || wait_for_http "http://127.0.0.1:8000/health" "127.0.0.1" 10; then
        _sys restart "${API_B_UNIT_NAME}.service" || true
      else
        echo "FAILED: API A unhealthy — not touching API B"
        return 1
      fi
    fi
    return $?
  fi
  if ! _sys is-active --quiet "${API_UNIT_NAME}.service" 2>/dev/null; then
    echo "API A not active — starting instead of reload"
    start_api
    return $?
  fi
  if _sys reload "${API_UNIT_NAME}.service"; then
    echo "API A reloaded gracefully (:8000 stays bound)"
  else
    echo "Warning: reload A failed — sequential restart"
    _sys restart "${API_UNIT_NAME}.service" || start_api_nohup
  fi
  if ! wait_for_http "http://127.0.0.1:8000/health" "api.voxbulk.com" 30 \
    && ! wait_for_http "http://127.0.0.1:8000/health" "127.0.0.1" 10; then
    echo "FAILED: API A /health after reload — not touching API B"
    return 1
  fi
  echo "API A healthy on :8000"
  if api_b_systemd_installed; then
    if ! _sys is-active --quiet "${API_B_UNIT_NAME}.service" 2>/dev/null; then
      echo "API B not active — starting"
      _sys start "${API_B_UNIT_NAME}.service" || true
    elif _sys reload "${API_B_UNIT_NAME}.service"; then
      echo "API B reloaded gracefully (:8001 stays bound)"
    else
      echo "Warning: reload B failed — sequential restart (A stays up)"
      _sys restart "${API_B_UNIT_NAME}.service" || true
    fi
    if wait_for_http "http://127.0.0.1:8001/health" "api.voxbulk.com" 30 \
      || wait_for_http "http://127.0.0.1:8001/health" "127.0.0.1" 10; then
      echo "API B healthy on :8001"
    else
      echo "Warning: API B /health failed — nginx will skip :8001 until it recovers"
    fi
  fi
  return 0
}

start_public_nohup() {
  cd "$PUBLIC_DIR"
  if [[ ! -d dist/client ]]; then
    echo "Building public frontend (first run)…"
    npm install
    npm run build
  fi
  local log="$PUBLIC_LOG"
  if [[ -e "$log" && ! -w "$log" ]]; then
    log="/tmp/voxbulk-public-qusay.log"
    echo "Warning: $PUBLIC_LOG not writable — logging to $log"
  fi
  : >>"$log" 2>/dev/null || true
  nohup npm run preview -- --host 127.0.0.1 --port 5173 >>"$log" 2>&1 &
  echo "Public site started via nohup on 127.0.0.1:5173 (log: $log)"
}

start_public() {
  if public_systemd_installed; then
    stop_public_processes
    if _sys start "${PUBLIC_UNIT_NAME}.service" || _sys restart "${PUBLIC_UNIT_NAME}.service"; then
      echo "Public site started via systemd ($PUBLIC_UNIT_NAME)"
      return 0
    fi
    echo "Warning: systemctl start $PUBLIC_UNIT_NAME failed — falling back to nohup"
  fi
  start_public_nohup
}

start_dashboard() {
  if skip_dashboard_preview; then
    echo "Skipping dashboard preview — production uses nginx static /www/wwwroot/dashboard.voxbulk.com"
    return
  fi
  cd "$DASH_DIR"
  if [[ "${VOX_SKIP_DASHBOARD_BUILD:-0}" != "1" ]]; then
    echo "Building dashboard (npm run build) …"
    npm install --silent 2>/dev/null || npm install
    npm run build
  elif [[ ! -d dist/client ]]; then
    echo "Building dashboard (first run)…"
    npm install
    npm run build
  fi
  local log="$DASH_LOG"
  if [[ -e "$log" && ! -w "$log" ]]; then
    log="/tmp/voxbulk-dashboard-qusay.log"
    echo "Warning: $DASH_LOG not writable — logging to $log"
  fi
  : >>"$log" 2>/dev/null || true
  nohup npm run preview -- --host 127.0.0.1 --port 5175 >>"$log" 2>&1 &
  echo "Dashboard started on 127.0.0.1:5175 (log: $log)"
}

install_service() {
  if [[ ! -f "$SETUP_SYSTEMD" ]]; then
    echo "Missing $SETUP_SYSTEMD"
    exit 1
  fi
  chmod +x "$SETUP_SYSTEMD" "$ROOT/scripts/run-public-preview.sh" 2>/dev/null || true
  if [[ "$(id -u)" -eq 0 ]]; then
    bash "$SETUP_SYSTEMD"
  elif command -v sudo >/dev/null 2>&1; then
    sudo bash "$SETUP_SYSTEMD"
  else
    echo "Need root or sudo to install systemd units"
    exit 1
  fi
}

status_systemd() {
  echo ""
  echo "=== Systemd (always-on) ==="
  if api_systemd_installed; then
    _sys --no-pager --full status "${API_UNIT_NAME}.service" 2>/dev/null | head -n 12 || true
    if _sys is-active --quiet "${API_UNIT_NAME}.service" 2>/dev/null; then
      echo "voxbulk-api: active (enabled on boot)"
    else
      echo "voxbulk-api: installed but not active — try: ./vox.sh start"
    fi
  else
    echo "voxbulk-api: not installed — run: ./vox.sh install-service"
  fi
  if api_b_systemd_installed; then
    if _sys is-active --quiet "${API_B_UNIT_NAME}.service" 2>/dev/null; then
      echo "voxbulk-api-b: active (:8001)"
    else
      echo "voxbulk-api-b: installed but not active"
    fi
  else
    echo "voxbulk-api-b: not installed — sudo bash scripts/vps-setup-api-systemd.sh"
  fi
  if public_systemd_installed; then
    if _sys is-active --quiet "${PUBLIC_UNIT_NAME}.service" 2>/dev/null; then
      echo "voxbulk-public: active (enabled on boot)"
    else
      echo "voxbulk-public: installed but not active"
    fi
  else
    echo "voxbulk-public: not installed"
  fi
}

status() {
  local wait_attempts="${1:-15}"
  local api_ok=0
  local public_ok=0
  local dashboard_ok=0

  status_systemd

  echo ""
  echo "=== API A (8000) ==="
  # Direct localhost check (works when TRUSTED_HOSTS is localhost-only on VPS)
  if wait_for_http "http://127.0.0.1:8000/health" "127.0.0.1" "$wait_attempts"; then
    curl -sf -H "Host: 127.0.0.1" http://127.0.0.1:8000/health && echo
    api_ok=1
  elif wait_for_http "http://127.0.0.1:8000/health" "api.voxbulk.com" "$wait_attempts"; then
    curl -sf -H "Host: api.voxbulk.com" http://127.0.0.1:8000/health && echo
    api_ok=1
  else
    echo "API A not responding on /health"
    show_log_tail "$API_LOG" "API A"
    echo "Tip: set TRUSTED_HOSTS=api.voxbulk.com,localhost,127.0.0.1 in voxbulk-api/.env if nginx uses Host: api.voxbulk.com"
  fi

  echo ""
  echo "=== API B (8001) ==="
  if api_b_systemd_installed; then
    if wait_for_http "http://127.0.0.1:8001/health" "api.voxbulk.com" "$wait_attempts" \
      || wait_for_http "http://127.0.0.1:8001/health" "127.0.0.1" "$wait_attempts"; then
      curl -sf -H "Host: api.voxbulk.com" http://127.0.0.1:8001/health 2>/dev/null \
        || curl -sf -H "Host: 127.0.0.1" http://127.0.0.1:8001/health
      echo
    else
      echo "API B not responding on /health — nginx will skip :8001 until it recovers"
    fi
  else
    echo "not installed"
  fi

  echo ""
  echo "=== Public ==="
  if skip_public_preview; then
    echo "Static wwwroot $PUBLIC_WWWROOT (no vite :5173 in production)"
    public_ok=1
  elif wait_for_http "http://127.0.0.1:5173/" "" "$wait_attempts"; then
    curl -sf -I http://127.0.0.1:5173/ | head -1
    public_ok=1
  else
    echo "Public preview not responding"
    show_log_tail "$PUBLIC_LOG" "public preview"
  fi

  echo ""
  echo "=== Dashboard ==="
  if skip_dashboard_preview; then
    echo "Static wwwroot /www/wwwroot/dashboard.voxbulk.com (no vite :5175 in production)"
    dashboard_ok=1
  elif wait_for_http "http://127.0.0.1:5175/" "" "$wait_attempts"; then
    curl -sf -I http://127.0.0.1:5175/ | head -1
    dashboard_ok=1
  else
    echo "Dashboard preview not responding"
    show_log_tail "$DASH_LOG" "dashboard preview"
  fi

  echo ""
  echo "=== Static admin (nginx wwwroot — not managed by vox.sh) ==="
  echo "  admin:      /www/wwwroot/admin.voxbulk.com"
  echo "  dashboard:  /www/wwwroot/dashboard.voxbulk.com"
  echo "  public:     $PUBLIC_WWWROOT (static)"
  echo "  Deploy UI:  ./deploy-vps.sh  (build + rsync + rolling API reload)"
  echo "  Always-on:  ./vox.sh install-service  (systemd Restart=always, ports 8000+8001)"

  echo ""
  echo "=== Processes ==="
  if api_systemd_installed; then
    systemctl is-active "${API_UNIT_NAME}.service" 2>/dev/null || true
  fi
  if api_b_systemd_installed; then
    systemctl is-active "${API_B_UNIT_NAME}.service" 2>/dev/null || true
  fi
  pgrep -af "gunicorn.*main:app" || true
  pgrep -af "uvicorn.*main:app" || echo "(no uvicorn master — gunicorn is normal in production)"
  ss -ltnp 2>/dev/null | grep -E ':8000|:8001|:5173|:5175' || netstat -ltnp 2>/dev/null | grep -E ':8000|:8001|:5173|:5175' || true
  pgrep -af "vite preview" || echo "no vite preview"
  status_celery || true

  if [[ "$api_ok" -eq 0 || "$public_ok" -eq 0 || "$dashboard_ok" -eq 0 ]]; then
    return 1
  fi
}

case "${1:-}" in
  start)
    start_api
    sleep 1
    if skip_public_preview; then
      echo "Public is static wwwroot ($PUBLIC_WWWROOT)"
      if public_systemd_installed; then
        _sys disable --now "${PUBLIC_UNIT_NAME}.service" 2>/dev/null || _sys stop "${PUBLIC_UNIT_NAME}.service" 2>/dev/null || true
      fi
      stop_public_processes
    else
      start_public
    fi
    start_dashboard
    sleep 2
    status
    ;;
  stop)
    stop_public
    stop_dashboard
    stop_api
    echo "Stopped API + public preview + dashboard preview"
    ;;
  restart)
    # Prefer rolling API reload so deploy never drops both :8000 and :8001.
    if [[ "${VOX_FORCE_API_RESTART:-0}" == "1" ]]; then
      echo "VOX_FORCE_API_RESTART=1 — sequential hard restart (never both units at once)"
      migrate_api_if_needed
      if api_systemd_installed; then
        if _sys restart "${API_UNIT_NAME}.service"; then
          echo "API A hard-restarted via systemd ($API_UNIT_NAME)"
        else
          echo "FAILED: systemctl restart A — leaving API B running (do not pkill gunicorn)"
        fi
      else
        echo "No systemd unit — sequential nohup on :8000 only"
        if command -v fuser >/dev/null 2>&1; then
          fuser -k 8000/tcp 2>/dev/null || true
        fi
        sleep 1
        start_api_nohup
      fi
      if ! wait_for_http "http://127.0.0.1:8000/health" "api.voxbulk.com" 30 \
        && ! wait_for_http "http://127.0.0.1:8000/health" "127.0.0.1" 10; then
        echo "FAILED: API A unhealthy after force restart — not touching API B"
      elif api_b_systemd_installed; then
        _sys restart "${API_B_UNIT_NAME}.service" || true
        echo "API B hard-restarted via systemd ($API_B_UNIT_NAME)"
      fi
    else
      reload_api
    fi
    if skip_public_preview; then
      echo "Skipping public vite preview — production uses nginx static $PUBLIC_WWWROOT"
      if public_systemd_installed; then
        _sys disable --now "${PUBLIC_UNIT_NAME}.service" 2>/dev/null || _sys stop "${PUBLIC_UNIT_NAME}.service" 2>/dev/null || true
      fi
      stop_public_processes
    elif [[ "${VOX_SKIP_PUBLIC_RESTART:-0}" != "1" ]]; then
      if public_systemd_installed; then
        _sys restart "${PUBLIC_UNIT_NAME}.service" || start_public_nohup
        echo "Public restarted via systemd ($PUBLIC_UNIT_NAME)"
      else
        stop_public
        sleep 1
        start_public
      fi
    else
      echo "Skipping public restart (VOX_SKIP_PUBLIC_RESTART=1)"
    fi
    stop_dashboard
    sleep 1
    start_dashboard
    if [[ "${VOX_SKIP_CELERY_RESTART:-0}" != "1" ]]; then
      restart_celery
    fi
    echo "Waiting for API A/B and static sites to become ready…"
    status || true
    ;;
  reload|reload-api|reload_api)
    reload_api
    ;;
  status)
    status
    ;;
  install-service|install_service)
    install_service
    ;;
  update|deploy)
    DEPLOY_SCRIPT="$ROOT/deploy-vps.sh"
    if [[ ! -f "$DEPLOY_SCRIPT" ]]; then
      echo "Missing $DEPLOY_SCRIPT"
      exit 1
    fi
    bash "$DEPLOY_SCRIPT"
    ;;
  sync-dashboard|dashboard)
    SYNC_SCRIPT="$ROOT/scripts/vps-sync-dashboard.sh"
    if [[ ! -f "$SYNC_SCRIPT" ]]; then
      echo "Missing $SYNC_SCRIPT"
      exit 1
    fi
    bash "$SYNC_SCRIPT"
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|reload|status|install-service|update|deploy|sync-dashboard|dashboard}"
    exit 1
    ;;
esac
