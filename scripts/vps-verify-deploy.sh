#!/usr/bin/env bash
# Prove which code revision is on disk and what the running API process serves.
# Run ON THE VPS: bash scripts/vps-verify-deploy.sh
#
# Optional:
#   VOX_SENTRY_TEST=1  send a Sentry test message if SENTRY_DSN is set
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$ROOT/voxbulk-api"
API_LOG="${VOX_API_LOG:-/tmp/voxbulk-api.log}"
MARKER="TELNYX_WEBHOOK_BUILD_MARKER_20260606_2250"
fail=0

_read_env_val() {
  local key="$1"
  local file="${2:-$API_DIR/.env}"
  grep -E "^${key}=" "$file" 2>/dev/null | tail -n1 | cut -d= -f2- | tr -d '\r' | sed 's/^["'\'']//;s/["'\'']$//' || true
}

echo "=== VoxBulk deploy verification ==="
echo "hostname: $(hostname)"
echo "time: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo ""

echo "--- git (repo on disk: $ROOT) ---"
cd "$ROOT"
git branch --show-current || true
git log -1 --oneline || true
REPO_HEAD="$(git rev-parse HEAD 2>/dev/null || true)"
REPO_SHORT="$(git rev-parse --short HEAD 2>/dev/null || true)"
echo "$REPO_HEAD"
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
    fail=1
  fi
done
echo ""

echo "--- running API process ---"
pgrep -af "uvicorn main:app|gunicorn" || echo "NO uvicorn/gunicorn process found"
echo ""

HEALTH_TOKEN="$(_read_env_val HEALTH_SECRET_TOKEN)"
HEALTH_JSON="/tmp/voxbulk-verify-health-build.json"
echo "--- /health/build (live process) ---"
set +e
if [[ -n "$HEALTH_TOKEN" ]]; then
  curl -sS -H "Host: api.voxbulk.com" -H "X-Health-Token: ${HEALTH_TOKEN}" \
    http://127.0.0.1:8000/health/build >"$HEALTH_JSON" 2>/tmp/voxbulk-verify-health.err
  curl_rc=$?
else
  curl -sS -H "Host: api.voxbulk.com" \
    http://127.0.0.1:8000/health/build >"$HEALTH_JSON" 2>/tmp/voxbulk-verify-health.err
  curl_rc=$?
fi
set -e
if [[ "$curl_rc" -ne 0 ]]; then
  echo "FAILED to reach /health/build (curl exit $curl_rc)"
  cat /tmp/voxbulk-verify-health.err 2>/dev/null || true
  fail=1
else
  python3 -m json.tool <"$HEALTH_JSON" || { echo "FAILED: /health/build was not JSON"; fail=1; }
  python3 - <<PY || fail=1
import json
import sys
from pathlib import Path
data = json.loads(Path("$HEALTH_JSON").read_text())
live_short = str(data.get("git_sha") or "").strip()
live_full = str(data.get("git_sha_full") or "").strip()
repo_short = "$REPO_SHORT"
repo_full = "$REPO_HEAD"
print("live git_sha=%s git_sha_full=%s" % (live_short, live_full))
print("disk HEAD short=%s full=%s" % (repo_short, repo_full))
if data.get("detail") == "Forbidden":
    print("FAILED: /health/build returned 403 — set HEALTH_SECRET_TOKEN and pass X-Health-Token")
    sys.exit(1)
if not data.get("deploy_ok"):
    print("FAILED: deploy_ok is not true")
    sys.exit(1)
match = False
if live_short and repo_short and live_short == repo_short:
    match = True
if live_full and repo_full and live_full == repo_full:
    match = True
if live_short and repo_full and repo_full.startswith(live_short):
    match = True
if not match:
    print("FAILED: /health/build git_sha does not match git rev-parse HEAD")
    sys.exit(1)
print("OK: running API git_sha matches repo HEAD")
PY
fi
echo ""

echo "--- Celery ping ---"
CELERY_BIN="$API_DIR/.venv/bin/celery"
if [[ -x "$CELERY_BIN" ]]; then
  if (cd "$API_DIR" && "$CELERY_BIN" -A app.workers.celery_app:celery_app inspect ping >/dev/null 2>&1); then
    echo "OK: celery inspect ping"
  else
    echo "FAILED: celery inspect ping — tail /tmp/voxbulk-celery.err.log"
    fail=1
  fi
else
  echo "FAILED: celery binary missing at $CELERY_BIN"
  fail=1
fi
echo ""

echo "--- Sentry ---"
SENTRY_DSN="$(_read_env_val SENTRY_DSN)"
if [[ -z "$SENTRY_DSN" ]]; then
  echo "skip: SENTRY_DSN unset (API Sentry is no-op)"
elif [[ "${VOX_SENTRY_TEST:-0}" == "1" ]]; then
  if (cd "$API_DIR" && "$API_DIR/.venv/bin/python" - <<'PY'
from app.core.sentry import init_sentry
import sentry_sdk
if not init_sentry():
    raise SystemExit("Sentry init failed despite SENTRY_DSN")
sentry_sdk.capture_message("voxbulk vps-verify-deploy Sentry test")
sentry_sdk.flush(timeout=5)
print("OK: sent Sentry test message")
PY
  ); then
    echo "OK: Sentry test event queued"
  else
    echo "FAILED: Sentry test event"
    fail=1
  fi
else
  echo "OK: SENTRY_DSN is set (not sending a test event; VOX_SENTRY_TEST=1 to send one)"
fi
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
    fail=1
  else
    echo "OK: fallback at line $line — new session-aware code on disk"
  fi
fi
echo ""
if [[ "$fail" -ne 0 ]]; then
  echo "FAILED. deploy_ok must be true and git_sha must match HEAD after restart."
  exit 1
fi
echo "Done. deploy_ok is true and git_sha matches repo HEAD."
