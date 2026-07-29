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

exec npm run preview -- --host 127.0.0.1 --port 5173
