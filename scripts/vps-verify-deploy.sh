#!/usr/bin/env bash
# Prove which code revision is on disk and what the running API process serves.
# Run ON THE VPS: bash scripts/vps-verify-deploy.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$ROOT/voxbulk-api"
API_LOG="${VOX_API_LOG:-/tmp/voxbulk-api.log}"
MARKER="TELNYX_WEBHOOK_BUILD_MARKER_20260606_2250"

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

echo "--- grep marker literal on disk ---"
grep -Rni "$MARKER" "$API_DIR" || echo "MISS: no files contain $MARKER"
echo ""

echo "--- build_info.json (deploy artifact, gitignored — expected untracked) ---"
if [[ -f "$API_DIR/build_info.json" ]]; then
  cat "$API_DIR/build_info.json"
else
  echo "MISSING: run ./deploy-vps.sh to write build_info.json"
fi
echo ""

echo "--- per-file marker anchors ---"
for f in \
  "$API_DIR/app/core/runtime_build_info.py" \
  "$API_DIR/main.py" \
  "$API_DIR/app/routers/telnyx.py" \
  "$API_DIR/app/services/telnyx_inbound_messaging_service.py"
do
  if grep -q "$MARKER" "$f" 2>/dev/null; then
    echo "OK  $f"
  else
    echo "MISS $f"
  fi
done
echo ""

echo "--- running API process ---"
pgrep -af "uvicorn main:app" || echo "NO uvicorn main:app process found"
echo ""

echo "--- /health/build (live process) ---"
curl -s http://127.0.0.1:8000/health/build | python3 -m json.tool || echo "FAILED to reach /health/build"
echo ""

echo "--- recent boot/webhook markers in API log ---"
if [[ -f "$API_LOG" ]]; then
  grep -E "$MARKER|app_boot|webhook_entry|router_dispatch|service_handle_webhook|awaiting_start_session_committed|active_recipient_matched" "$API_LOG" | tail -n 25 || echo "(no marker lines — run: cd $ROOT && ./vox.sh restart)"
else
  echo "Log not found: $API_LOG"
fi
echo ""

echo "--- fallback line sanity (old code ~450, new code ~510+) ---"
if grep -n "inbound_fallback_after_survey_miss" "$API_DIR/app/services/telnyx_inbound_messaging_service.py" >/dev/null 2>&1; then
  line=$(grep -n "inbound_fallback_after_survey_miss" "$API_DIR/app/services/telnyx_inbound_messaging_service.py" | head -1 | cut -d: -f1)
  if [[ "$line" -lt 490 ]]; then
    echo "WARNING: fallback at line $line — likely OLD telnyx_inbound_messaging_service.py on disk"
  else
    echo "OK: fallback at line $line — new session-aware code on disk"
  fi
fi
echo ""
echo "Done. deploy_ok must be true in /health/build after restart."
