#!/usr/bin/env bash
# Rewrite WA survey templates for Meta UTILITY and optionally push to Telnyx.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Missing $ROOT/.venv — create it first:" >&2
  echo "  cd $ROOT && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/rewrite_wa_survey_templates_for_utility.py" "$@"
