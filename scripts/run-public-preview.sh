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

# Vite preview always writes bundled config under node_modules/.vite-temp (TMPDIR is ignored).
# Root-owned leftovers from a prior sudo deploy cause EACCES crash-loops under systemd (User=qusay).
# Never rely on interactive sudo here — the unit runs as User=qusay with no TTY.
_vite_temp="$PUBLIC_DIR/node_modules/.vite-temp"
if [[ -d "$PUBLIC_DIR/node_modules" ]]; then
  _ensure_vite_temp() {
    mkdir -p "$_vite_temp" 2>/dev/null || true
    [[ -d "$_vite_temp" && -w "$_vite_temp" ]]
  }

  if ! _ensure_vite_temp; then
    echo "[voxbulk-public] $_vite_temp not writable — recovering …" >&2
    # Parent node_modules is often qusay-owned while .vite-temp is root:755 — mv works, rm may not.
    if [[ -w "$PUBLIC_DIR/node_modules" ]]; then
      mv "$_vite_temp" "${_vite_temp}.root-stale.$$" 2>/dev/null || true
      rm -rf "$_vite_temp" 2>/dev/null || true
    fi
    # Best-effort passwordless sudo (NOPASSWD); ignore failure / auth noise.
    if command -v sudo >/dev/null 2>&1; then
      sudo -n chown -R "$(id -un):$(id -gn)" "$_vite_temp" 2>/dev/null \
        || sudo -n chown -R "$(id -un):$(id -gn)" "$PUBLIC_DIR/node_modules" 2>/dev/null \
        || true
      sudo -n rm -rf "$_vite_temp" 2>/dev/null || true
    fi
    _ensure_vite_temp || true
  fi

  if [[ ! -d "$_vite_temp" || ! -w "$_vite_temp" ]]; then
    echo "[voxbulk-public] FAIL: cannot write $_vite_temp. Run once: sudo chown -R $(whoami) $PUBLIC_DIR/node_modules && sudo rm -rf $_vite_temp" >&2
    exit 1
  fi

  # Drop stale root leftovers from prior recoveries (best-effort).
  find "$PUBLIC_DIR/node_modules" -maxdepth 1 -type d -name '.vite-temp.root-stale.*' \
    -user "$(id -un)" -exec rm -rf {} + 2>/dev/null || true
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
