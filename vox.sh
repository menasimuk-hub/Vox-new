#!/usr/bin/env bash
# VOXBULK VPS — start / stop / restart API + public site (nginx serves admin/dashboard static)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$ROOT/voxbulk-api"
PUBLIC_DIR="$ROOT/voxbulk.com/frontend"
DASH_DIR="$ROOT/dashboard.voxbulk.com/dashboard-web"
API_LOG="${VOX_API_LOG:-/tmp/voxbulk-api.log}"
PUBLIC_LOG="${VOX_PUBLIC_LOG:-/tmp/voxbulk-public.log}"
DASH_LOG="${VOX_DASH_LOG:-/tmp/voxbulk-dashboard.log}"

# Avoid root-owned /tmp logs blocking non-root deploys (same class of bug as deploy markers).
ensure_log_file() {
  local var_name="$1"
  local current="${!var_name}"
  if touch "$current" 2>/dev/null; then
    return 0
  fi
  local fallback="/tmp/voxbulk-$(id -u)-$(basename "$current")"
  if touch "$fallback" 2>/dev/null; then
    printf -v "$var_name" '%s' "$fallback"
    return 0
  fi
  fallback="$ROOT/.deploy/$(basename "$current")"
  mkdir -p "$ROOT/.deploy" 2>/dev/null || true
  touch "$fallback" 2>/dev/null || true
  printf -v "$var_name" '%s' "$fallback"
}

port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | grep -qE ":${port}\\s" && return 0
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 && return 0
  fi
  # Fallback: try connect (works even without ss/lsof)
  (echo >/dev/tcp/127.0.0.1/"$port") >/dev/null 2>&1 && return 0
  return 1
}

stop_api() {
  echo "Stopping API on :8000 …"
  pkill -f "uvicorn.*main:app" 2>/dev/null || true
  local i=0
  while (( i < 12 )); do
    if ! pgrep -f "uvicorn.*main:app" >/dev/null 2>&1 && ! port_in_use 8000; then
      echo "API stopped"
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  echo "Force-killing leftover uvicorn on :8000 …"
  pkill -9 -f "uvicorn.*main:app" 2>/dev/null || true
  # Last resort: kill whatever still listens on 8000
  if command -v fuser >/dev/null 2>&1; then
    fuser -k 8000/tcp >/dev/null 2>&1 || true
  fi
  sleep 1
  if port_in_use 8000; then
    echo "WARNING: port 8000 still in use — start may fail"
  else
    echo "API stopped"
  fi
}

stop_public() {
  pkill -f "vite preview.*5173" 2>/dev/null || true
  pkill -f "npm run preview.*5173" 2>/dev/null || true
}

stop_dashboard() {
  pkill -f "vite preview.*5175" 2>/dev/null || true
  pkill -f "npm run preview.*5175" 2>/dev/null || true
}

celery_supervisor_name() {
  if command -v supervisorctl >/dev/null 2>&1 && supervisorctl status voxbulk-celery >/dev/null 2>&1; then
    echo "voxbulk-celery"
    return 0
  fi
  if command -v supervisorctl >/dev/null 2>&1 && supervisorctl status retover-celery >/dev/null 2>&1; then
    echo "retover-celery"
    return 0
  fi
  return 1
}

celery_beat_supervisor_name() {
  if command -v supervisorctl >/dev/null 2>&1 && supervisorctl status voxbulk-celery-beat >/dev/null 2>&1; then
    echo "voxbulk-celery-beat"
    return 0
  fi
  return 1
}

restart_celery() {
  if ! command -v supervisorctl >/dev/null 2>&1; then
    echo "supervisorctl not found — install Celery via: sudo bash scripts/vps-setup-celery.sh"
    return
  fi
  local name beat
  if name="$(celery_supervisor_name)"; then
    supervisorctl restart "$name" && echo "Celery worker restarted ($name)"
  else
    echo "Celery not in supervisor — run once: sudo bash scripts/vps-setup-celery.sh"
    echo "  (Required for WA voice-note transcription, billing jobs, webhooks)"
  fi
  if beat="$(celery_beat_supervisor_name)"; then
    supervisorctl restart "$beat" && echo "Celery beat restarted ($beat)"
  else
    echo "Celery beat not in supervisor — run: sudo bash scripts/vps-setup-celery.sh"
  fi
}

status_celery() {
  echo ""
  echo "=== Celery (WA voice notes, async jobs, billing beat) ==="
  if ! command -v supervisorctl >/dev/null 2>&1; then
    echo "supervisorctl not installed"
    return 1
  fi
  local name beat ok=0
  if name="$(celery_supervisor_name)"; then
    supervisorctl status "$name" || true
    if supervisorctl status "$name" 2>/dev/null | grep -q RUNNING; then
      ok=1
    fi
  else
    echo "voxbulk-celery not configured — run: sudo bash scripts/vps-setup-celery.sh"
  fi
  if beat="$(celery_beat_supervisor_name)"; then
    supervisorctl status "$beat" || true
    if supervisorctl status "$beat" 2>/dev/null | grep -q RUNNING; then
      ok=1
    fi
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
  if redis-cli ping >/dev/null 2>&1; then
    echo "redis: PONG"
  else
    echo "redis: not responding (CELERY_BROKER_URL)"
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

start_api() {
  ensure_log_file API_LOG
  cd "$API_DIR"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  if port_in_use 8000; then
    echo "Port 8000 busy — stopping previous API first"
    stop_api
  fi
  # deploy-vps.sh already runs alembic; skip here to avoid MySQL metadata lock hangs.
  if [[ "${VOX_SKIP_MIGRATE:-0}" != "1" ]]; then
    echo "Running alembic upgrade head …"
    python -m alembic upgrade head || echo "Warning: alembic upgrade failed — API will retry migrations on boot"
  else
    echo "Skipping alembic (VOX_SKIP_MIGRATE=1)"
  fi
  nohup uvicorn main:app --host 127.0.0.1 --port 8000 --workers "${VOX_UVICORN_WORKERS:-1}" >>"$API_LOG" 2>&1 &
  local pid=$!
  echo "API starting pid=$pid (log: $API_LOG)"
  # Fail fast if process dies immediately
  sleep 1
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "API process exited immediately — last log lines:"
    show_log_tail "$API_LOG" "API"
    return 1
  fi
}

start_public() {
  ensure_log_file PUBLIC_LOG
  cd "$PUBLIC_DIR"
  if [[ ! -d dist/client ]]; then
    echo "Building public frontend (first run)…"
    npm install
    npm run build
  fi
  nohup npm run preview -- --host 127.0.0.1 --port 5173 >>"$PUBLIC_LOG" 2>&1 &
  echo "Public site started on 127.0.0.1:5173 (log: $PUBLIC_LOG)"
}

start_dashboard() {
  if [[ "${VOX_SKIP_DASHBOARD_PREVIEW:-0}" == "1" ]]; then
    echo "Skipping dashboard preview (VOX_SKIP_DASHBOARD_PREVIEW=1 — nginx serves static wwwroot)"
    return
  fi
  ensure_log_file DASH_LOG
  cd "$DASH_DIR"
  # Deploy already built dashboard into wwwroot — skip rebuild on API restart unless forced.
  if [[ "${VOX_SKIP_DASHBOARD_BUILD:-0}" == "1" ]]; then
    if [[ ! -d dist/client ]]; then
      echo "Building dashboard (missing dist/client) …"
      npm install --silent 2>/dev/null || npm install
      npm run build
    fi
  else
    echo "Building dashboard (npm run build) …"
    npm install --silent 2>/dev/null || npm install
    npm run build
  fi
  nohup npm run preview -- --host 127.0.0.1 --port 5175 >>"$DASH_LOG" 2>&1 &
  echo "Dashboard started on 127.0.0.1:5175 (log: $DASH_LOG)"
}

status() {
  local wait_attempts="${1:-15}"
  local api_ok=0
  local public_ok=0
  local dashboard_ok=0

  echo "=== API (8000) ==="
  # Direct localhost check (works when TRUSTED_HOSTS is localhost-only on VPS)
  if wait_for_http "http://127.0.0.1:8000/health" "127.0.0.1" "$wait_attempts"; then
    curl -sf -H "Host: 127.0.0.1" http://127.0.0.1:8000/health && echo
    api_ok=1
  elif wait_for_http "http://127.0.0.1:8000/health" "api.voxbulk.com" "$wait_attempts"; then
    curl -sf -H "Host: api.voxbulk.com" http://127.0.0.1:8000/health && echo
    api_ok=1
  else
    echo "API not responding on /health"
    show_log_tail "$API_LOG" "API"
    echo "Tip: set TRUSTED_HOSTS=api.voxbulk.com,localhost,127.0.0.1 in voxbulk-api/.env if nginx uses Host: api.voxbulk.com"
  fi

  echo ""
  echo "=== Public (5173) ==="
  if wait_for_http "http://127.0.0.1:5173/" "" "$wait_attempts"; then
    curl -sf -I http://127.0.0.1:5173/ | head -1
    public_ok=1
  else
    echo "Public preview not responding"
    show_log_tail "$PUBLIC_LOG" "public preview"
  fi

  echo ""
  echo "=== Dashboard (5175) ==="
  if [[ "${VOX_SKIP_DASHBOARD_PREVIEW:-0}" == "1" ]]; then
    echo "Skipped (VOX_SKIP_DASHBOARD_PREVIEW=1 — static wwwroot via nginx)"
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
  echo "  dashboard:  /www/wwwroot/dashboard.voxbulk.com (static) or 127.0.0.1:5175 preview in dev"
  echo "  Deploy UI:  ./deploy-vps.sh  (build + rsync admin + restart)"

  echo ""
  echo "=== Processes ==="
  pgrep -af "uvicorn.*main:app" || echo "no uvicorn"
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
    start_public
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
    stop_public
    stop_dashboard
    stop_api
    sleep 1
    # Production: nginx serves admin/dashboard static wwwroot — skip slow dashboard rebuild.
    export VOX_SKIP_DASHBOARD_BUILD="${VOX_SKIP_DASHBOARD_BUILD:-1}"
    export VOX_SKIP_DASHBOARD_PREVIEW="${VOX_SKIP_DASHBOARD_PREVIEW:-1}"
    start_api || {
      show_log_tail "$API_LOG" "API"
      exit 1
    }
    sleep 2
    start_public
    start_dashboard
    restart_celery
    echo "Waiting for API (and previews if enabled) to become ready…"
    status 45 || true
    ;;
  status)
    status
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
    echo "Usage: $0 {start|stop|restart|status|update|deploy|sync-dashboard|dashboard}"
    exit 1
    ;;
esac
