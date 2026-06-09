#!/usr/bin/env bash
# Idempotent WA survey industry seed — uses API virtualenv (SQLAlchemy 2.x).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Missing $ROOT/.venv — create it first:" >&2
  echo "  cd /www/voxbulk && VOX_GIT_BRANCH=fix/wa-interview-platform-templates ./deploy-vps.sh" >&2
  echo "  # or: cd $ROOT && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/seed_wa_survey_industries.py" "$@"
