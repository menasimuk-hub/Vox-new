#!/usr/bin/env bash
# Force-push local WA survey template drafts to Meta (same name, batched).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Missing $ROOT/.venv — create venv and pip install -r requirements.txt first." >&2
  exit 1
fi
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/push_force_update_wa_templates_batch.py" "$@"
