#!/usr/bin/env bash
# Seed care & repair WA + AI call demo surveys for HubSpot sync testing.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Missing voxbulk-api/.venv — create it first." >&2
  exit 1
fi
exec "$PY" scripts/seed_demo_survey_hubspot.py "$@"
