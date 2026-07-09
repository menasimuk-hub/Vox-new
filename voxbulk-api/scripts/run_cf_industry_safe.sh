#!/usr/bin/env bash
# Safe chunked Customer Feedback push for ONE industry.
# Pushes each language row: Meta 99 (primary) → pause → Telnyx 55 (backup mirror).
#
# Usage (on VPS):
#   cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
#   chmod +x scripts/run_cf_industry_safe.sh
#   ./scripts/run_cf_industry_safe.sh hotel
#   ./scripts/run_cf_industry_safe.sh hotel --dry-run
#
# Keep running after SSH disconnect — use tmux (recommended):
#   tmux new -s cf-push
#   cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
#   ./scripts/run_cf_industry_safe.sh hotel 2>&1 | tee /tmp/cf-hotel-$(date +%Y%m%d).log
#   # Detach: Ctrl+B then D
#   # Reattach later: tmux attach -t cf-push
#
set -euo pipefail

INDUSTRY_SLUG="${1:?Usage: $0 <industry-slug> [--dry-run]}"
DRY_RUN=""
if [[ "${2:-}" == "--dry-run" ]]; then
  DRY_RUN="--dry-run"
fi

# Conservative anti-spam defaults (Meta + Telnyx dual push per language row)
LANG_BATCH=2
DELAY_SEC=30
PROFILE_DELAY_SEC=60
TOPICS_PER_RUN=1
PAUSE_BETWEEN_TOPICS_SEC=90

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .venv/bin/activate ]]; then
  echo "ERROR: .venv not found — run from voxbulk-api on VPS" >&2
  exit 1
fi
# shellcheck source=/dev/null
source .venv/bin/activate

STATE_FILE="seed-data/customer-feedback/push-reports/chunk-state/${INDUSTRY_SLUG}.json"
LOG_DIR="/tmp/voxbulk-cf-push"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/cf-${INDUSTRY_SLUG}-$(date +%Y%m%d-%H%M%S).log"

echo "=== CF safe push: ${INDUSTRY_SLUG} ===" | tee -a "$LOG_FILE"
echo "Meta primary → Telnyx backup | lang-batch=${LANG_BATCH} delay=${DELAY_SEC}s profile-delay=${PROFILE_DELAY_SEC}s" | tee -a "$LOG_FILE"
echo "Log: ${LOG_FILE}" | tee -a "$LOG_FILE"
echo "PID: $$ | Started: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$LOG_FILE"

RUN=0
while true; do
  RUN=$((RUN + 1))
  echo "" | tee -a "$LOG_FILE"
  echo "--- Run #${RUN} $(date -u +%Y-%m-%dT%H:%M:%SZ) ---" | tee -a "$LOG_FILE"

  set +e
  python -u scripts/push_cf_service_chunked.py \
    --industry-slug "$INDUSTRY_SLUG" \
    --continue \
    --topics-per-run "$TOPICS_PER_RUN" \
    --lang-batch "$LANG_BATCH" \
    --delay-sec "$DELAY_SEC" \
    --profile-delay-sec "$PROFILE_DELAY_SEC" \
    --pull-after-topic \
    $DRY_RUN 2>&1 | tee -a "$LOG_FILE"
  EC=${PIPESTATUS[0]}
  set -e

  if [[ "$EC" -ne 0 ]]; then
    echo "STOPPED: script exited ${EC} — fix errors, then re-run same command (state saved)." | tee -a "$LOG_FILE"
    exit "$EC"
  fi

  if [[ ! -f "$STATE_FILE" ]]; then
    echo "DONE: industry ${INDUSTRY_SLUG} complete (state file removed)." | tee -a "$LOG_FILE"
    exit 0
  fi

  echo "Topic batch done — pausing ${PAUSE_BETWEEN_TOPICS_SEC}s before next topic…" | tee -a "$LOG_FILE"
  sleep "$PAUSE_BETWEEN_TOPICS_SEC"
done
