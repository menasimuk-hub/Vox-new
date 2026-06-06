#!/usr/bin/env bash
# Prove which code revision is on disk and what the running API process serves.
# Run ON THE VPS: bash scripts/vps-verify-deploy.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$ROOT/voxbulk-api"
API_LOG="${VOX_API_LOG:-/tmp/voxbulk-api.log}"

echo "=== VoxBulk deploy verification ==="
echo "hostname: $(hostname)"
echo "time: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo ""

echo "--- git (repo on disk: $ROOT) ---"
cd "$ROOT"
git branch --show-current || true
git log -1 --oneline || true
git rev-parse HEAD || true
git status --short || true
echo ""

echo "--- build_info.json ---"
if [[ -f "$API_DIR/build_info.json" ]]; then
  cat "$API_DIR/build_info.json"
else
  echo "MISSING: $API_DIR/build_info.json (run deploy-vps.sh write_build_info)"
fi
echo ""

echo "--- source markers on disk (grep) ---"
for needle in \
  ensure_awaiting_start_session \
  find_active_recipient_for_inbound \
  awaiting_start_session_committed \
  start_survey_transition \
  welcome_sent_but_no_active_session \
  survey_session_bug \
  TELNYX_WEBHOOK_BUILD_MARKER_20260606_2250
do
  if grep -rq "$needle" "$API_DIR/app/services" 2>/dev/null; then
    echo "OK  $needle"
  else
    echo "MISS $needle"
  fi
done
echo ""

echo "--- running API process ---"
pgrep -af "uvicorn main:app" || echo "NO uvicorn main:app process found"
echo ""

echo "--- /health/build (live process) ---"
curl -sf -H "Host: api.voxbulk.com" http://127.0.0.1:8000/health/build 2>/dev/null | python3 -m json.tool || \
curl -sf http://127.0.0.1:8000/health/build 2>/dev/null | python3 -m json.tool || \
echo "FAILED to reach /health/build on :8000"
echo ""

echo "--- recent boot/webhook markers in API log ---"
if [[ -f "$API_LOG" ]]; then
  grep -E "TELNYX_WEBHOOK_BUILD_MARKER|app_boot|webhook_entry|awaiting_start_session_committed|active_recipient_matched" "$API_LOG" | tail -n 20 || echo "(no marker lines yet — restart API and trigger webhook)"
else
  echo "Log not found: $API_LOG"
fi
echo ""

echo "--- line-number sanity (old vs new fallback path) ---"
if grep -n "inbound_fallback_after_survey_miss" "$API_DIR/app/services/telnyx_inbound_messaging_service.py"; then
  line=$(grep -n "inbound_fallback_after_survey_miss" "$API_DIR/app/services/telnyx_inbound_messaging_service.py" | head -1 | cut -d: -f1)
  if [[ "$line" -lt 480 ]]; then
    echo "WARNING: fallback log is on line $line — likely OLD code (new code is ~494+)"
  else
    echo "OK: fallback log line $line suggests NEW code loaded on disk"
  fi
fi
echo ""
echo "Done. If disk markers OK but /health/build deploy_ok=false or webhook marker missing in logs, restart: cd $ROOT && ./vox.sh restart"
