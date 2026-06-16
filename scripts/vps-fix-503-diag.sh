#!/usr/bin/env bash
# One-shot 503 diagnostic for the Telnyx WhatsApp webhook on the VPS.
#
# Forces git working tree to match origin/<branch>, hard-restarts uvicorn,
# fires a fake Telnyx inbound, then greps /tmp/voxbulk-api.log for the most
# likely outcomes and prints a single VERDICT line we can act on.
#
# Run as root from the repo root:
#   sudo bash scripts/vps-fix-503-diag.sh
#
# Env overrides:
#   VOX_BRANCH=feat/dashboard-ai-assistant-v1   (target branch to reset to)
#   VOX_API_LOG=/tmp/voxbulk-api.log
#   VOX_TO_PHONE=+972500000000                  (your YallaSay WA number)
#   VOX_FROM_PHONE=+972500000099                (fake customer number for smoke test)
#   VOX_SKIP_RESET=1                            (skip git reset --hard step)

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_LOG="${VOX_API_LOG:-/tmp/voxbulk-api.log}"
BRANCH="${VOX_BRANCH:-feat/dashboard-ai-assistant-v1}"
TO_PHONE="${VOX_TO_PHONE:-+972500000000}"
FROM_PHONE="${VOX_FROM_PHONE:-+972500000099}"
SKIP_RESET="${VOX_SKIP_RESET:-0}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

step()    { echo -e "${CYAN}[diag]${NC} $*"; }
info()    { echo -e "${GREEN}[diag]${NC} $*"; }
warn()    { echo -e "${YELLOW}[diag]${NC} $*"; }
fail()    { echo -e "${RED}[diag]${NC} $*" >&2; }
verdict() { echo -e "\n${GREEN}VERDICT:${NC} $*\n"; }

cd "$ROOT"

step "1/6 pre-state"
echo "  repo root:   $ROOT"
echo "  branch:      $BRANCH"
echo "  api_log:     $API_LOG"
echo "  current HEAD:  $(git rev-parse --short HEAD 2>/dev/null || echo unknown) ($(git rev-parse HEAD 2>/dev/null || echo unknown))"
echo "  working tree:"
git status --short | head -n 20 || true
echo "  uvicorn PIDs (before): $(pgrep -af 'uvicorn main:app' 2>/dev/null | wc -l) found"
pgrep -af "uvicorn main:app" 2>/dev/null || echo "    (none)"

if [[ "$SKIP_RESET" != "1" ]]; then
  step "2/6 fetch + hard reset to origin/$BRANCH"
  if ! git fetch origin "$BRANCH"; then
    fail "git fetch origin $BRANCH failed"
    verdict "fetch_failed - check git remote and network"
    exit 1
  fi
  REMOTE_SHA="$(git rev-parse "origin/$BRANCH")"
  LOCAL_SHA="$(git rev-parse HEAD)"
  echo "  remote:  $REMOTE_SHA"
  echo "  local:   $LOCAL_SHA"
  if [[ "$REMOTE_SHA" != "$LOCAL_SHA" ]]; then
    warn "local != remote, hard-resetting"
    git reset --hard "origin/$BRANCH"
  else
    info "local already matches remote"
  fi
else
  warn "2/6 SKIPPED (VOX_SKIP_RESET=1)"
fi

step "3/6 hard restart uvicorn (pkill -9 + ./vox.sh start)"
pkill -f "uvicorn main:app" 2>/dev/null || true
sleep 1
# Belt-and-braces: hard kill anything still alive
if pgrep -f "uvicorn main:app" >/dev/null 2>&1; then
  warn "soft kill did not stop uvicorn, sending SIGKILL"
  pkill -9 -f "uvicorn main:app" 2>/dev/null || true
  sleep 1
fi
if pgrep -f "uvicorn main:app" >/dev/null 2>&1; then
  fail "uvicorn still running after SIGKILL"
  pgrep -af "uvicorn main:app"
  verdict "stale_uvicorn_pid - manual intervention required"
  exit 1
fi
info "all uvicorn PIDs stopped"

# Start via vox.sh if available, otherwise start uvicorn directly
if [[ -x "$ROOT/vox.sh" ]]; then
  # vox.sh start brings up frontend too; we only want api. Inline the API start to keep it fast.
  if [[ -d "$ROOT/voxbulk-api/.venv" ]]; then
    (
      cd "$ROOT/voxbulk-api"
      # shellcheck disable=SC1091
      source .venv/bin/activate
      VOX_SKIP_MIGRATE="${VOX_SKIP_MIGRATE:-0}" nohup uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1 \
        >>"$API_LOG" 2>&1 &
      disown || true
    )
    info "uvicorn launched (background)"
  else
    fail "voxbulk-api/.venv missing — run ./deploy-vps.sh first"
    verdict "venv_missing - cannot start uvicorn"
    exit 1
  fi
else
  fail "vox.sh missing at $ROOT/vox.sh"
  exit 1
fi

step "4/6 wait for /health (max 25s)"
HEALTH_OK=0
for i in $(seq 1 25); do
  if curl -sf -H "Host: 127.0.0.1" http://127.0.0.1:8000/health >/dev/null 2>&1; then
    HEALTH_OK=1
    info "/health responding after ${i}s"
    break
  fi
  sleep 1
done
if [[ "$HEALTH_OK" -ne 1 ]]; then
  fail "/health never came up"
  echo "--- tail $API_LOG ---"
  tail -n 60 "$API_LOG" 2>/dev/null || true
  verdict "api_did_not_start - paste the tail above"
  exit 1
fi

# Confirm new code loaded by probing /health/abuu-runtime for fields shipped recently.
HEALTH_JSON="$(curl -s http://127.0.0.1:8000/health/abuu-runtime || echo '{}')"
echo "  /health/abuu-runtime: $HEALTH_JSON"
if ! echo "$HEALTH_JSON" | grep -q '"smart_agent_enabled"'; then
  warn "new health fields missing — code is older than b8bffbd"
fi

step "5/6 fire smoke webhook (fake WhatsApp inbound)"
NOW_EPOCH="$(date +%s)"
PAYLOAD=$(cat <<JSON
{"data":{"event_type":"message.received","id":"diag-$NOW_EPOCH","payload":{"id":"diag-msg-$NOW_EPOCH","type":"WhatsApp","direction":"inbound","text":"diag smoke test","from":{"phone_number":"$FROM_PHONE"},"to":[{"phone_number":"$TO_PHONE"}]}}}
JSON
)
echo "  payload: $PAYLOAD"
CURL_OUT="$(curl -s -o /tmp/diag-resp.json -w '%{http_code}' -X POST \
  -H 'content-type: application/json' \
  -d "$PAYLOAD" \
  http://127.0.0.1:8000/telnyx/webhooks/messages || true)"
RESP_BODY="$(cat /tmp/diag-resp.json 2>/dev/null || echo '')"
echo "  response: HTTP $CURL_OUT  body=$RESP_BODY"
sleep 3

step "6/6 classify result from $API_LOG"
PATTERN='db_operational_error|db_programming_error|smart_agent_(text|voice)_failed|smart_agent_(gate|text|voice)_rollback|abuu_wa_inbound_handler_failed|router_dispatch|service_handle_webhook|unhandled_exception|Traceback'
RECENT_LINES="$(grep -E "$PATTERN" "$API_LOG" 2>/dev/null | tail -n 60 || true)"
echo "--- last matching log lines ---"
echo "$RECENT_LINES" | tail -n 30
echo "--- end log lines ---"

# Classify by the most-specific match first
if echo "$RECENT_LINES" | grep -q 'db_operational_error'; then
  SQL=$(echo "$RECENT_LINES" | grep -E 'db_operational_error' | tail -n 1 | sed -E 's/.*sql_error=(["'"'"'][^"'"'"']*["'"'"']).*/\1/' | head -c 240)
  verdict "db_operational_error sql=$SQL  -> paste this whole line back to me"
  exit 0
fi
if echo "$RECENT_LINES" | grep -q 'db_programming_error'; then
  SQL=$(echo "$RECENT_LINES" | grep -E 'db_programming_error' | tail -n 1 | sed -E 's/.*sql_error=(["'"'"'][^"'"'"']*["'"'"']).*/\1/' | head -c 240)
  verdict "db_programming_error sql=$SQL  -> paste this whole line back to me"
  exit 0
fi
if echo "$RECENT_LINES" | grep -q 'smart_agent_text_failed_falling_back_to_agent\|smart_agent_voice_failed_falling_back_to_agent'; then
  verdict "smart_agent_failed_fallback_to_legacy -> smart-agent code raised, legacy agent should have replied. paste the Traceback line above"
  exit 0
fi
if echo "$RECENT_LINES" | grep -q 'abuu_wa_inbound_handler_failed'; then
  verdict "abuu_wa_inbound_handler_failed -> inbound dispatch raised. paste the line above"
  exit 0
fi
if echo "$RECENT_LINES" | grep -q 'unhandled_exception'; then
  verdict "unhandled_exception (non-DB) -> paste the Traceback line above"
  exit 0
fi
if echo "$RECENT_LINES" | grep -q 'service_handle_webhook\|router_dispatch'; then
  # Reached the handler but no error logged + curl returned 2xx
  if [[ "$CURL_OUT" =~ ^2 ]]; then
    verdict "success - request reached handler and returned $CURL_OUT. smart_agent is live"
    exit 0
  else
    verdict "handler_reached_but_error_swallowed - new code may not be loaded. curl=$CURL_OUT body=$RESP_BODY"
    exit 0
  fi
fi

verdict "no_log_activity - new code likely still not loaded. ps aux | grep uvicorn (check timestamp) and try again with VOX_SKIP_RESET=1"
exit 0
