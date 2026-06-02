#!/usr/bin/env bash
# Full VPS interview E2E — HTTP-only, email-safe, 3 min slot, real call, log + JSON report.
# Does NOT open the app database (avoids blocking SMTP/email while the test runs).
# Usage: bash scripts/e2e_interview_workflow_test.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAMP="$(date -u +%Y%m%d-%H%M%S)"
LOG="${VOXBULK_E2E_LOG:-/tmp/voxbulk-e2e-interview-${STAMP}.log}"
REPORT="${VOXBULK_E2E_REPORT:-/tmp/voxbulk-e2e-report-${STAMP}.json}"

PY=""
for candidate in "$ROOT/.venv/bin/python3" "$ROOT/venv/bin/python3" "$(command -v python3)"; do
  if [[ -n "$candidate" && -x "$candidate" ]]; then
    PY="$candidate"
    break
  fi
done

if [[ -z "$PY" ]]; then
  echo "ERROR: python3 not found" >&2
  exit 1
fi

echo "Using: $PY"
echo "Log:    $LOG"
echo "Report: $REPORT"
echo "Mode:   email-safe (WhatsApp invites; SMTP stays free for manual sends)"

exec "$PY" "$ROOT/scripts/e2e_interview_workflow_test.py" \
  --slot-minutes-ahead 3 \
  --log-file "$LOG" \
  --report-file "$REPORT" \
  "$@" \
  2>&1 | tee -a "$LOG"
