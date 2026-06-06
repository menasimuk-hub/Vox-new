#!/usr/bin/env bash
# VOXBULK VPS — start / stop / restart API + public site (nginx serves admin/dashboard static)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$ROOT/voxbulk-api"
PUBLIC_DIR="$ROOT/voxbulk.com/frontend"
DASH_DIR="$ROOT/dashboard.voxbulk.com/dashboard-web"
API_LOG="/tmp/voxbulk-api.log"
PUBLIC_LOG="/tmp/voxbulk-public.log"
DASH_LOG="/tmp/voxbulk-dashboard.log"

stop_api() {
  pkill -f "uvicorn main:app --host 127.0.0.1 --port 8000" 2>/dev/null || true
  pkill -f "uvicorn main:app" 2>/dev/null || true
}

stop_public() {
  pkill -f "vite preview.*5173" 2>/dev/null || true
  pkill -f "npm run preview.*5173" 2>/dev/null || true
}

stop_dashboard() {
  pkill -f "vite preview.*5175" 2>/dev/null || true
  pkill -f "npm run preview.*5175" 2>/dev/null || true
}

restart_celery() {
  if ! command -v supervisorctl >/dev/null 2>&1; then
    return
  fi
  if supervisorctl status retover-celery >/dev/null 2>&1; then
    supervisorctl restart retover-celery && echo "Celery restarted (retover-celery)"
  else
    echo "Celery not configured in supervisor (optional — only needed for background invoice/email jobs)"
  fi
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
  cd "$API_DIR"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  nohup uvicorn main:app --host 127.0.0.1 --port 8000 >>"$API_LOG" 2>&1 &
  echo "API started (log: $API_LOG)"
}

start_public() {
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
  if wait_for_http "http://127.0.0.1:5175/" "" "$wait_attempts"; then
    curl -sf -I http://127.0.0.1:5175/ | head -1
    dashboard_ok=1
  else
    echo "Dashboard preview not responding"
    show_log_tail "$DASH_LOG" "dashboard preview"
  fi

  echo ""
  echo "=== Static admin (nginx wwwroot — not managed by vox.sh) ==="
  echo "  admin:      /www/wwwroot/admin.voxbulk.com"
  echo "  dashboard:  nginx must proxy to 127.0.0.1:5175 (TanStack Start — not static wwwroot)"
  echo "  Deploy UI:  ./deploy-vps.sh  (build + rsync admin + restart)"

  echo ""
  echo "=== Processes ==="
  pgrep -af "uvicorn main:app" || echo "no uvicorn"
  pgrep -af "vite preview" || echo "no vite preview"

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
    start_api
    sleep 2
    start_public
    start_dashboard
    restart_celery
    echo "Waiting for API, public preview, and dashboard preview to become ready…"
    status || true
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
