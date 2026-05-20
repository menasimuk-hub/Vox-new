#!/usr/bin/env bash
# VOXBULK VPS — start / stop / restart API + public site (nginx serves admin/dashboard static)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$ROOT/voxbulk-api"
PUBLIC_DIR="$ROOT/voxbulk.com/frontend"
API_LOG="/tmp/voxbulk-api.log"
PUBLIC_LOG="/tmp/voxbulk-public.log"

stop_api() {
  pkill -f "uvicorn main:app --host 127.0.0.1 --port 8000" 2>/dev/null || true
  pkill -f "uvicorn main:app" 2>/dev/null || true
}

stop_public() {
  pkill -f "vite preview.*5173" 2>/dev/null || true
  pkill -f "npm run preview.*5173" 2>/dev/null || true
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
  nohup npm run preview -- --host 127.0.0.1 --port 5173 >>"$PUBLIC_LOG" 2>&1 &
  echo "Public site started (log: $PUBLIC_LOG)"
}

status() {
  echo "=== API (8000) ==="
  curl -sf -H "Host: api.voxbulk.com" http://127.0.0.1:8000/health && echo || echo "API not responding"
  echo ""
  echo "=== Public (5173) ==="
  curl -sf -I http://127.0.0.1:5173/ | head -1 || echo "Public preview not responding"
  echo ""
  echo "=== Processes ==="
  pgrep -af "uvicorn main:app" || echo "no uvicorn"
  pgrep -af "vite preview" || echo "no vite preview"
}

case "${1:-}" in
  start)
    start_api
    sleep 1
    start_public
    sleep 2
    status
    ;;
  stop)
    stop_public
    stop_api
    echo "Stopped API + public preview"
    ;;
  restart)
    stop_public
    stop_api
    sleep 1
    start_api
    sleep 1
    start_public
    sleep 2
    status
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
  *)
    echo "Usage: $0 {start|stop|restart|status|update|deploy}"
    exit 1
    ;;
esac
