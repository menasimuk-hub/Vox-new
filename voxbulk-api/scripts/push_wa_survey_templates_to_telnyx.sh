#!/usr/bin/env bash
# Push WA Survey WhatsApp templates to Telnyx/Meta.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Missing $ROOT/.venv — create it first:" >&2
  echo "  cd $ROOT && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/push_wa_survey_templates_to_telnyx.py" "$@"
