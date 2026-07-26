#!/usr/bin/env bash
# Organized Telnyx 55 catalog mirror:
#   1) Customer Feedback — one industry to completion (stop on hard fail)
#   2) Survey + system_buttoned — Telnyx backup only
# Meta 99: CF skips when already linked (no force). Telnyx 55: force mirror.
#
# Usage (VPS):
#   cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
#   bash scripts/run_telnyx55_mirror_safe.sh
#   bash scripts/run_telnyx55_mirror_safe.sh --industry-slug restaurant
#   bash scripts/run_telnyx55_mirror_safe.sh --skip-survey
#   bash scripts/run_telnyx55_mirror_safe.sh --skip-cf   # survey only
#
# tmux:
#   tmux new -s telnyx55-mirror
#   cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
#   bash scripts/run_telnyx55_mirror_safe.sh
#   # Detach: Ctrl+B then D
#
set -euo pipefail

DRY_RUN=0
SKIP_SURVEY=0
SKIP_CF=0
INDUSTRY_SLUG=""
SURVEY_DELAY_SEC="${SURVEY_DELAY_SEC:-25}"
SURVEY_BATCH_SIZE="${SURVEY_BATCH_SIZE:-5}"
PAUSE_BETWEEN_INDUSTRIES_SEC="${PAUSE_BETWEEN_INDUSTRIES_SEC:-120}"

# Junk / empty auto-slugs (never push)
SKIP_INDUSTRY_REGEX='^industry-[0-9]+$'

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --skip-survey) SKIP_SURVEY=1; shift ;;
    --skip-cf) SKIP_CF=1; shift ;;
    --industry-slug)
      INDUSTRY_SLUG="${2:-}"
      if [[ -z "$INDUSTRY_SLUG" ]]; then
        echo "ERROR: --industry-slug requires a value" >&2
        exit 2
      fi
      shift 2
      ;;
    *)
      echo "Unknown arg: $1" >&2
      echo "Usage: $0 [--dry-run] [--skip-survey] [--skip-cf] [--industry-slug SLUG]" >&2
      exit 2
      ;;
  esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .venv/bin/activate ]]; then
  echo "ERROR: .venv not found — run from voxbulk-api on VPS" >&2
  exit 1
fi
# shellcheck source=/dev/null
source .venv/bin/activate

LOG_DIR="/tmp/voxbulk-telnyx-mirror"
mkdir -p "$LOG_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${LOG_DIR}/mirror-${STAMP}.log"
STATUS_FILE="${LOG_DIR}/status-${STAMP}.txt"

log() {
  echo "$@" | tee -a "$LOG_FILE"
}

fail_stop() {
  log "STOPPED: $*"
  echo "stopped $(date -u +%Y-%m-%dT%H:%M:%SZ) reason=$*" >"$STATUS_FILE"
  echo "log=${LOG_FILE}" >>"$STATUS_FILE"
  exit 1
}

log "=== Telnyx 55 organized catalog mirror ==="
log "Started: $(date -u +%Y-%m-%dT%H:%M:%SZ) PID=$$"
log "Log: ${LOG_FILE}"
log "dry_run=${DRY_RUN} skip_survey=${SKIP_SURVEY} skip_cf=${SKIP_CF} industry_slug=${INDUSTRY_SLUG:-all}"
log "survey_delay=${SURVEY_DELAY_SEC}s survey_batch=${SURVEY_BATCH_SIZE}"
echo "running" >"$STATUS_FILE"
echo "log=${LOG_FILE}" >>"$STATUS_FILE"

log ""
log "--- Phase 0: diag counts ---"
set +e
python -u scripts/diag_wa_profile_matrix_counts.py --service survey 2>&1 | tee -a "$LOG_FILE"
python -u scripts/diag_wa_profile_matrix_counts.py --service customer_feedback 2>&1 | tee -a "$LOG_FILE"
set -e

# ---------------------------------------------------------------------------
# Phase B first: Customer Feedback (one industry fully → next; stop on fail)
# ---------------------------------------------------------------------------
if [[ "$SKIP_CF" -eq 0 ]]; then
  log ""
  log "--- Phase B: Customer Feedback (organized, one industry to completion) ---"
  mapfile -t INDUSTRIES < <(
    python - <<'PY'
from sqlalchemy import select
from app.core.database import get_sessionmaker
from app.models.customer_feedback import FeedbackIndustry

with get_sessionmaker()() as db:
    rows = db.scalars(
        select(FeedbackIndustry).order_by(FeedbackIndustry.sort_order, FeedbackIndustry.name)
    ).all()
    for row in rows:
        slug = (getattr(row, "slug", None) or "").strip()
        if slug:
            print(slug)
PY
  )

  if [[ -n "$INDUSTRY_SLUG" ]]; then
    INDUSTRIES=("$INDUSTRY_SLUG")
  fi

  log "Industries queued: ${#INDUSTRIES[@]}"
  for slug in "${INDUSTRIES[@]}"; do
    [[ -z "$slug" ]] && continue
    if [[ "$slug" =~ $SKIP_INDUSTRY_REGEX ]]; then
      log "SKIP junk industry slug: ${slug}"
      continue
    fi

    log ""
    log "=== CF industry: ${slug} ==="
    if [[ "$DRY_RUN" -eq 1 ]]; then
      set +e
      python -u scripts/push_cf_service_chunked.py \
        --industry-slug "$slug" \
        --topics-per-run 1 \
        --lang-batch 2 \
        --delay-sec 30 \
        --profile-delay-sec 60 \
        --dry-run \
        2>&1 | tee -a "$LOG_FILE"
      set -e
      log "(dry-run) skipping full industry loop for ${slug}"
      continue
    fi

    # Always use bash — ignore executable bit (Windows git checkout often drops +x)
    set +e
    bash scripts/run_cf_industry_safe.sh "$slug" 2>&1 | tee -a "$LOG_FILE"
    EC=${PIPESTATUS[0]}
    set -e
    if [[ "$EC" -ne 0 ]]; then
      fail_stop "industry ${slug} exited ${EC} — fix error, then re-run with --industry-slug ${slug} (state saved)"
    fi
    log "Industry ${slug} complete."
    log "Pausing ${PAUSE_BETWEEN_INDUSTRIES_SEC}s before next industry…"
    sleep "$PAUSE_BETWEEN_INDUSTRIES_SEC"
  done
else
  log "Skipping CF (--skip-cf)"
fi

# ---------------------------------------------------------------------------
# Phase A after CF: survey + system → Telnyx only
# ---------------------------------------------------------------------------
if [[ "$SKIP_SURVEY" -eq 0 ]]; then
  log ""
  log "--- Phase A: survey + system_buttoned → Telnyx backup only ---"
  DRY_FLAG=()
  if [[ "$DRY_RUN" -eq 1 ]]; then
    DRY_FLAG=(--dry-run)
  fi
  set +e
  python -u scripts/mirror_survey_system_to_telnyx_backup.py \
    --scope both \
    --delay-sec "$SURVEY_DELAY_SEC" \
    --batch-size "$SURVEY_BATCH_SIZE" \
    "${DRY_FLAG[@]}" \
    2>&1 | tee -a "$LOG_FILE"
  EC=${PIPESTATUS[0]}
  set -e
  if [[ "$EC" -ne 0 ]]; then
    fail_stop "survey/system mirror exited ${EC}"
  fi
else
  log "Skipping survey/system (--skip-survey)"
fi

log ""
log "--- Phase C: final diag ---"
set +e
python -u scripts/diag_wa_profile_matrix_counts.py --service survey 2>&1 | tee -a "$LOG_FILE"
python -u scripts/diag_wa_profile_matrix_counts.py --service customer_feedback 2>&1 | tee -a "$LOG_FILE"
set -e

log "Finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "finished $(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$STATUS_FILE"
echo "log=${LOG_FILE}" >>"$STATUS_FILE"
log "Status: ${STATUS_FILE}"
log "DONE"
