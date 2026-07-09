#!/usr/bin/env bash
# Queue ALL Customer Feedback industries one-by-one (safest full-catalog push).
# Each industry: Meta 99 primary → Telnyx 55 backup, small language batches + long pauses.
#
# Usage (on VPS inside tmux — see below):
#   cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
#   chmod +x scripts/run_cf_industry_safe.sh scripts/run_cf_all_industries_safe.sh
#   ./scripts/run_cf_all_industries_safe.sh
#   ./scripts/run_cf_all_industries_safe.sh --dry-run
#   ./scripts/run_cf_all_industries_safe.sh --from retail   # skip earlier slugs
#
# SSH + keep running (copy/paste):
#
#   ssh qusay@voxbulk.com
#   tmux new -s cf-all
#   cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
#   git pull origin main
#   ./scripts/run_cf_all_industries_safe.sh 2>&1 | tee /tmp/cf-all-industries.log
#   # Detach: press Ctrl+B, then D
#   # Close laptop — job keeps running
#   # Later: ssh again → tmux attach -t cf-all
#
# Alternative without tmux (nohup):
#   nohup ./scripts/run_cf_all_industries_safe.sh > /tmp/cf-all-industries.log 2>&1 &
#   tail -f /tmp/cf-all-industries.log
#
set -euo pipefail

DRY_RUN=""
FROM_SLUG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN="--dry-run"
      shift
      ;;
    --from)
      FROM_SLUG="${2:?--from requires industry slug}"
      shift 2
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

# Default industry order (matches seed catalog). Override with --from <slug> to resume.
INDUSTRIES=(
  restaurant
  retail
  salon
  hotel
  others
  fitness
  events
)

PAUSE_BETWEEN_INDUSTRIES_SEC=600

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
chmod +x scripts/run_cf_industry_safe.sh

LOG_DIR="/tmp/voxbulk-cf-push"
mkdir -p "$LOG_DIR"
MASTER_LOG="${LOG_DIR}/cf-all-industries-$(date +%Y%m%d-%H%M%S).log"

echo "=== CF safe push: ALL industries ===" | tee "$MASTER_LOG"
echo "Order: ${INDUSTRIES[*]}" | tee -a "$MASTER_LOG"
echo "Pause between industries: ${PAUSE_BETWEEN_INDUSTRIES_SEC}s" | tee -a "$MASTER_LOG"
echo "Started: $(date -u +%Y-%m-%dT%H:%M:%SZ) PID=$$" | tee -a "$MASTER_LOG"

SKIP=true
if [[ -z "$FROM_SLUG" ]]; then
  SKIP=false
fi

for slug in "${INDUSTRIES[@]}"; do
  if [[ "$SKIP" == true ]]; then
    if [[ "$slug" == "$FROM_SLUG" ]]; then
      SKIP=false
    else
      echo "Skipping ${slug} (--from ${FROM_SLUG})" | tee -a "$MASTER_LOG"
      continue
    fi
  fi

  echo "" | tee -a "$MASTER_LOG"
  echo "========== INDUSTRY: ${slug} ==========" | tee -a "$MASTER_LOG"

  set +e
  ./scripts/run_cf_industry_safe.sh "$slug" $DRY_RUN 2>&1 | tee -a "$MASTER_LOG"
  EC=${PIPESTATUS[0]}
  set -e

  if [[ "$EC" -ne 0 ]]; then
    echo "FAILED on industry ${slug} — resume with:" | tee -a "$MASTER_LOG"
    echo "  ./scripts/run_cf_all_industries_safe.sh --from ${slug}" | tee -a "$MASTER_LOG"
    echo "  or fix and: ./scripts/run_cf_industry_safe.sh ${slug}" | tee -a "$MASTER_LOG"
    exit "$EC"
  fi

  echo "Industry ${slug} complete. Sleeping ${PAUSE_BETWEEN_INDUSTRIES_SEC}s before next…" | tee -a "$MASTER_LOG"
  sleep "$PAUSE_BETWEEN_INDUSTRIES_SEC"
done

echo "" | tee -a "$MASTER_LOG"
echo "ALL INDUSTRIES DONE $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$MASTER_LOG"
