#!/usr/bin/env bash
# Seed mixed feedback responses for the Ealing location (compare QA).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/seed_feedback_responses_mixed.py" \
  --email zaghlolno@gmail.com \
  --location-name ealing \
  --count 80 \
  --seed 43 \
  --clear \
  "$@"
