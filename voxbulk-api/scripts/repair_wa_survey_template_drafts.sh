#!/usr/bin/env bash
# Repair invalid WA Survey template drafts (bad Meta BODY examples in DB).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Missing $ROOT/.venv — create it first:" >&2
  echo "  cd $ROOT && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/repair_wa_survey_template_drafts.py" "$@"
