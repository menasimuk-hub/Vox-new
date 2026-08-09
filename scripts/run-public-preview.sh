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

# Vite preview loads vite.config.ts via a temp write under node_modules/.vite-temp.
# Root-owned leftovers from a prior sudo deploy cause EACCES crash-loops under systemd (User=qusay).
# Never rely on interactive sudo here — the unit runs as User=qusay with no TTY.
_vite_temp="$PUBLIC_DIR/node_modules/.vite-temp"
_vite_fallback="${TMPDIR:-/tmp}/voxbulk-vite-temp-$(id -un)"
if [[ -d "$PUBLIC_DIR/node_modules" ]]; then
  # Drop a root-owned temp dir when we can recreate it as the service user.
  if [[ -e "$_vite_temp" && ! -w "$_vite_temp" ]]; then
    echo "[voxbulk-public] $_vite_temp not writable — recreating …" >&2
    rm -rf "$_vite_temp" 2>/dev/null || true
  fi
  mkdir -p "$_vite_temp" 2>/dev/null || true
  if [[ ! -w "$_vite_temp" ]]; then
    echo "[voxbulk-public] using fallback vite temp: $_vite_fallback" >&2
    mkdir -p "$_vite_fallback"
    export TMPDIR="$_vite_fallback"
    # Best-effort passwordless sudo (NOPASSWD); ignore failure.
    if command -v sudo >/dev/null 2>&1; then
      sudo -n chown -R "$(id -un):$(id -gn)" "$_vite_temp" 2>/dev/null \
        || sudo -n chown -R "$(id -un):$(id -gn)" "$PUBLIC_DIR/node_modules" 2>/dev/null \
        || true
      mkdir -p "$_vite_temp" 2>/dev/null || true
    fi
  fi
  if [[ ! -d "$_vite_temp" || ! -w "$_vite_temp" ]]; then
    if [[ ! -d "$_vite_fallback" || ! -w "$_vite_fallback" ]]; then
      echo "[voxbulk-public] FAIL: cannot write vite temp. Run once: sudo chown -R $(whoami) $PUBLIC_DIR/node_modules" >&2
      exit 1
    fi
  fi
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
