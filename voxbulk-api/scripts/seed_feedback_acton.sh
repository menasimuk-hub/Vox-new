#!/usr/bin/env bash
# Seed 120 mixed feedback responses for the Acon location (compare QA).
# Note: location is stored as "Acon" in the dashboard (not "Acton").
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/seed_feedback_responses_mixed.py" \
  --email zaghlolno@gmail.com \
  --location-name acon \
  --count 120 \
  --clear \
  "$@"
