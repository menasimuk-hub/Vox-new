#!/usr/bin/env bash
# Retry all queued WA survey voice-note transcription jobs (no HTTP auth — runs on VPS).
#
# Usage:
#   cd /www/voxbulk
#   chmod +x scripts/retry-pending-voice-notes.sh
#   ./scripts/retry-pending-voice-notes.sh
#   ./scripts/retry-pending-voice-notes.sh --status pending
#   ./scripts/retry-pending-voice-notes.sh --order-id YOUR_ORDER_UUID
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$ROOT/voxbulk-api"
STATUSES="pending,failed,retrying"
ORDER_ID=""
LIMIT=200

while [[ $# -gt 0 ]]; do
  case "$1" in
    --status) STATUSES="$2"; shift 2 ;;
    --order-id) ORDER_ID="$2"; shift 2 ;;
    --limit) LIMIT="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--status pending,failed] [--order-id UUID] [--limit N]"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

cd "$API_DIR"
# shellcheck disable=SC1091
source .venv/bin/activate

export RETRY_STATUSES="$STATUSES"
export RETRY_ORDER_ID="$ORDER_ID"
export RETRY_LIMIT="$LIMIT"

python <<'PY'
import os
import sys

sys.path.insert(0, os.getcwd())

from app.core.database import get_sessionmaker
from app.services.survey_wa_voice_note_service import SurveyWaVoiceNoteService

statuses = tuple(
    s.strip().lower()
    for s in (os.environ.get("RETRY_STATUSES") or "pending,failed,retrying").split(",")
    if s.strip()
)
order_id = (os.environ.get("RETRY_ORDER_ID") or "").strip() or None
limit = int(os.environ.get("RETRY_LIMIT") or "200")

db = get_sessionmaker()()
try:
    result = SurveyWaVoiceNoteService.retry_queued_jobs(
        db,
        statuses=statuses,
        order_id=order_id,
        limit=limit,
    )
finally:
    db.close()

print(f"Retried {result['retried_count']} job(s) (statuses={result['statuses']})")
for jid in result.get("job_ids") or []:
    print(f"  - {jid}")
if not result["retried_count"]:
    print("No matching jobs — nothing to do.")
PY
