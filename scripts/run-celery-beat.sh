#!/usr/bin/env bash
# Run Celery beat scheduler (used by supervisor: voxbulk-celery-beat).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$ROOT/voxbulk-api"
CELERY_BIN="$API_DIR/.venv/bin/celery"

if [[ ! -x "$CELERY_BIN" ]]; then
  echo "Celery not found at $CELERY_BIN — run: cd $API_DIR && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

cd "$API_DIR"
exec "$CELERY_BIN" -A app.workers.celery_app:celery_app beat -l INFO
