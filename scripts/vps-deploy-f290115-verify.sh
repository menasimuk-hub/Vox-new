#!/usr/bin/env bash
# Pull f290115+, deploy API, print all verification artifacts in one run.
# Usage on VPS: bash scripts/vps-deploy-f290115-verify.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
MARKER="TELNYX_WEBHOOK_BUILD_MARKER_20260606_2250"
API_LOG="/tmp/voxbulk-api.log"

echo "========== 1) GIT PULL =========="
git fetch origin fix/wa-interview-platform-templates
git checkout fix/wa-interview-platform-templates
git pull --ff-only origin fix/wa-interview-platform-templates
git log -1 --oneline
git rev-parse HEAD

echo ""
echo "========== 2) DEPLOY + RESTART =========="
VOX_GIT_BRANCH=fix/wa-interview-platform-templates VOX_SKIP_BUILD=1 ./deploy-vps.sh

echo ""
echo "========== 3) MARKER ON DISK =========="
grep -Rni "$MARKER" /www/voxbulk/voxbulk-api || true

echo ""
echo "========== 4) /health/build =========="
curl -s http://127.0.0.1:8000/health/build | python3 -m json.tool

echo ""
echo "========== 5) BOOT MARKER LOGS (last 20) =========="
grep "$MARKER" "$API_LOG" | tail -20 || echo "(none yet)"

echo ""
echo "========== 6) NEXT: Step 5 send test + click Start, then run: =========="
echo "grep -E '$MARKER|awaiting_start|active_recipient|start_survey_transition|first_question_sent|welcome_sent_but_no_active_session|survey_session_bug' $API_LOG | tail -40"
