#!/usr/bin/env bash
# API process for systemd — gunicorn + uvicorn workers (supports graceful reload).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$ROOT/voxbulk-api"
cd "$API_DIR"

GUNICORN_BIN="$API_DIR/.venv/bin/gunicorn"
UVICORN_BIN="$API_DIR/.venv/bin/uvicorn"
# 2+ workers keep at least one worker serving during `systemctl reload`
WORKERS="${VOX_UVICORN_WORKERS:-${VOX_GUNICORN_WORKERS:-2}}"
HOST="${VOX_API_HOST:-127.0.0.1}"
PORT="${VOX_API_PORT:-8000}"

if [[ -x "$GUNICORN_BIN" ]]; then
  exec "$GUNICORN_BIN" main:app \
    -k uvicorn.workers.UvicornWorker \
    --bind "${HOST}:${PORT}" \
    --workers "$WORKERS" \
    --timeout 120 \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile -
fi

# Fallback if gunicorn not installed yet
exec "$UVICORN_BIN" main:app --host "$HOST" --port "$PORT" --workers "$WORKERS"
