#!/usr/bin/env bash
# Push all remaining Customer Feedback templates to Meta 99 only (~24h safe pace).
#
# Usage (VPS):
#   cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
#   chmod +x scripts/run_cf_all_remaining_meta.sh
#
#   ./scripts/run_cf_all_remaining_meta.sh --status
#   ./scripts/run_cf_all_remaining_meta.sh
#   ./scripts/run_cf_all_remaining_meta.sh --target-hours 24 --start-industry hotel
#
# tmux (recommended):
#   tmux new -s cf-meta99
#   cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
#   ./scripts/run_cf_all_remaining_meta.sh 2>&1 | tee /tmp/cf-meta99-all.log
#   # Ctrl+B D to detach
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .venv/bin/activate ]]; then
  echo "ERROR: .venv not found — run from voxbulk-api on VPS" >&2
  exit 1
fi
# shellcheck source=/dev/null
source .venv/bin/activate

exec python -u scripts/push_cf_all_remaining_meta.py "$@"
