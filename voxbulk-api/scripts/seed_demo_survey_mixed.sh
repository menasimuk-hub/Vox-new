#!/usr/bin/env bash
# Seed mixed WA + AI Call survey demo data (synthetic contacts only).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate
exec python scripts/seed_demo_survey_mixed.py "$@"
