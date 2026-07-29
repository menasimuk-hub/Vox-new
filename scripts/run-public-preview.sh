#!/usr/bin/env bash
# Public site vite preview — used by systemd unit voxbulk-public.service
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PUBLIC_DIR="$ROOT/voxbulk.com/frontend"
cd "$PUBLIC_DIR"

if [[ ! -d dist/client ]]; then
  echo "[voxbulk-public] dist/client missing — run npm run build in $PUBLIC_DIR" >&2
  exit 1
fi

# Free :5173 if an orphan nohup/vite preview still holds it (systemd would otherwise
# crash-loop with "Port 5173 is already in use" and Sign in can look broken).
if command -v fuser >/dev/null 2>&1; then
  fuser -k 5173/tcp >/dev/null 2>&1 || true
  sleep 1
elif command -v lsof >/dev/null 2>&1; then
  # shellcheck disable=SC2046
  kill -TERM $(lsof -t -iTCP:5173 -sTCP:LISTEN 2>/dev/null) 2>/dev/null || true
  sleep 1
else
  pkill -f "vite preview.*5173" 2>/dev/null || true
  pkill -f "npm run preview.*5173" 2>/dev/null || true
  sleep 1
fi

exec npm run preview -- --host 127.0.0.1 --port 5173
