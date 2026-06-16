#!/usr/bin/env bash
# Abuu WhatsApp one-shot diagnostic — prints to terminal immediately (no tee redirect).
# Run ON THE VPS after sending a test message to +447822002099 (Number 2).
#
# Usage:
#   cd /www/voxbulk
#   bash scripts/vps-abuu-diag.sh
#   bash scripts/vps-abuu-diag.sh --follow   # tail live trace while you send WA
#
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$ROOT/voxbulk-api"
API_LOG="${VOX_API_LOG:-/tmp/voxbulk-api.log}"
FOLLOW=0

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

section() { echo -e "\n${GREEN}=== $* ===${NC}"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*" >&2; }
fail_hint() { echo -e "${RED}[fix]${NC} $*" >&2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --follow|-f) FOLLOW=1; shift ;;
    -h|--help)
      echo "Usage: bash scripts/vps-abuu-diag.sh [--follow]"
      exit 0
      ;;
    *) warn "Unknown arg: $1"; shift ;;
  esac
done

section "Git + API health"
GIT_HEAD=""
if [[ -d "$ROOT/.git" ]]; then
  GIT_HEAD="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo "")"
  git -C "$ROOT" log -1 --oneline 2>/dev/null || warn "git log failed"
else
  warn "Not a git repo: $ROOT"
fi

HEALTH_SHA=""
if curl -sf --max-time 5 http://127.0.0.1:8000/health/abuu-runtime >/tmp/vox-abuu-health.json 2>/dev/null; then
  python3 -m json.tool /tmp/vox-abuu-health.json
  HEALTH_SHA="$(python3 -c "import json; print(json.load(open('/tmp/vox-abuu-health.json')).get('git_sha',''))" 2>/dev/null || echo "")"
else
  fail_hint "API not responding on :8000 — run: cd $ROOT && ./vox.sh restart"
fi

if [[ -n "$GIT_HEAD" && -n "$HEALTH_SHA" && "$GIT_HEAD" != "$HEALTH_SHA" ]]; then
  fail_hint "API stale: disk=$GIT_HEAD but /health says $HEALTH_SHA — run:"
  echo "  echo '{\"git_sha\":\"'$GIT_HEAD'\",\"git_branch\":\"'$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)'\",\"built_at\":\"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'\"}' > $API_DIR/build_info.json"
  echo "  cd $ROOT && ./vox.sh restart"
fi

section "Telnyx numbers (Number 1 surveys / Number 2 Abuu) — no API keys"
if [[ ! -d "$API_DIR/.venv" ]]; then
  fail_hint "Missing $API_DIR/.venv"
else
  # shellcheck disable=SC1091
  source "$API_DIR/.venv/bin/activate"
  cd "$API_DIR"
  python3 - <<'PY'
from app.core.database import get_sessionmaker
from app.services.yallasay_telnyx_line import (
    get_yallasay_whatsapp_e164,
    get_yallasay_line_config,
    is_yallasay_line,
)
from app.services.provider_settings import ProviderSettingsService

with get_sessionmaker()() as db:
    cfg, en = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
    cfg = cfg if isinstance(cfg, dict) else {}
    yalla = get_yallasay_whatsapp_e164(db)
    line = get_yallasay_line_config(db)
    wa_profile = line.get("whatsapp_messaging_profile_id") or ""
    raw_sms_p2 = str(cfg.get("sms_messaging_profile_id_2") or "").strip()
    raw_wa_p2 = str(cfg.get("whatsapp_messaging_profile_id_2") or "").strip()
    print("telnyx_integration_enabled:", en)
    print("Number_1_whatsapp_from (surveys):", cfg.get("whatsapp_from") or "(not set)")
    print("Number_2_sms_from_2:", cfg.get("sms_from_2") or "(not set)")
    print("Number_2_whatsapp_from_2:", cfg.get("whatsapp_from_2") or "(not set)")
    print("yallasay_wa_resolved:", yalla or "(NOT SET — Abuu will not route!)")
    print("yallasay_wa_profile_id:", wa_profile or "(NOT SET — sends may fail!)")
    print("survey_wa_profile_id:", cfg.get("whatsapp_messaging_profile_id") or "(not set)")
    for n in ("+447822002099", "+447822002055"):
        print(f"is_yallasay_line({n}):", is_yallasay_line(db, n))

    bad_profile = False
    for label, raw in (("sms_messaging_profile_id_2", raw_sms_p2), ("whatsapp_messaging_profile_id_2", raw_wa_p2)):
        if raw and ProviderSettingsService.looks_like_phone_not_profile(raw):
            print(f"FAIL: {label} is a phone number ({raw}) — must be Telnyx profile UUID")
            bad_profile = True
    if bad_profile:
        print("\n>>> FIX: Admin → Telnyx → clear Yallasay profile field → Apply Telnyx setup → Save")
    elif not yalla:
        print("\n>>> FIX: Admin → Telnyx → Number 2 = +447822002099 → Save → Apply Telnyx setup")
    elif not wa_profile:
        print("\n>>> FIX: Set Yallasay messaging profile ID or click Apply Telnyx setup")
PY
fi

section "DeepSeek + DeepInfra (agent + voice STT)"
if [[ -d "$API_DIR/.venv" ]]; then
  cd "$API_DIR"
  python3 - <<'PY'
from app.core.database import get_sessionmaker
from app.abuu.agent.agent import _deepseek_platform_ready
from app.services.providers.deepinfra_service import DeepInfraProviderService

with get_sessionmaker()() as db:
    ds = _deepseek_platform_ready(db)
    di = DeepInfraProviderService.is_configured(db)
    print("deepseek_ready (agent):", ds)
    print("deepinfra_configured (voice STT):", di)
    if not ds:
        print(">>> FIX: Admin → Integrations → DeepSeek — enable + API key")
PY
fi

section "API process + log file"
pgrep -af "uvicorn main:app" || warn "no uvicorn process"
if [[ -f "$API_LOG" ]]; then
  echo "Log: $API_LOG ($(wc -l < "$API_LOG") lines)"
else
  warn "Log missing: $API_LOG"
fi

section "Recent Abuu / Yallasay log lines (last 5 minutes, then tail 40)"
if [[ -f "$API_LOG" ]]; then
  RECENT="$(grep -E 'yallasay_inbound_route|yallasay_inbound_handler_failed|abuu_wa_trace|abuu_live_trace|abuu_wa_reply_failed|abuu_agent_deepseek|telnyx_message_http_error|abuu_stt_all_providers' "$API_LOG" 2>/dev/null | python3 -c "
import sys
from datetime import datetime, timedelta, timezone
cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
for line in sys.stdin:
    if '\"timestamp\":' not in line:
        continue
    try:
        ts = line.split('\"timestamp\": \"', 1)[1].split('\"', 1)[0]
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        if dt >= cutoff:
            print(line.rstrip())
    except Exception:
        pass
" || true)"
  if [[ -n "$RECENT" ]]; then
    echo "--- last 5 minutes ---"
    echo "$RECENT"
  else
    warn "no Abuu lines in last 5 minutes — send Yallasay to +447822002099 while running: bash scripts/vps-abuu-diag.sh --follow"
  fi
  echo "--- tail 40 (all time) ---"
  grep -E 'yallasay_inbound_route|yallasay_inbound_handler_failed|abuu_wa_trace|abuu_live_trace|abuu_wa_reply_failed|abuu_agent_deepseek|telnyx_message_http_error|abuu_stt_all_providers' "$API_LOG" 2>/dev/null | tail -40 || true
else
  warn "no log file"
fi

section "Recent inbound webhooks (last 10)"
if [[ -f "$API_LOG" ]]; then
  grep -E 'TELNYX_WEBHOOK_BUILD_MARKER|message.received|survey_wa_inbound_route' "$API_LOG" 2>/dev/null | tail -10 || warn "no webhook lines"
fi

section "Interpretation"
cat <<'EOF'
Expected when working:
  - yallasay_wa_resolved: +447822002099
  - is_yallasay_line(+447822002099): True
  - After you send "Yallasay" to 099:
      yallasay_inbound_route ... abuu_handled=True
      abuu_wa_trace IN ...
      abuu_wa_trace OUT ... ok=True

If IN but OUT ok=False → Telnyx send failed (profile/number/opt-out).
If no IN at all → webhook not reaching API (Telnyx WABA on 099).
If is_yallasay_line(099) False → Admin Number 2 not saved.
If yallasay_wa_profile_id starts with + → wrong config (phone saved as profile UUID).
If git HEAD != health git_sha → run ./vox.sh restart after git pull.
EOF

section "VPS quick fixes (if diag shows problems)"
cat <<'EOF'
1. Stale API after git pull:
   cd /www/voxbulk
   echo '{"git_sha":"'$(git rev-parse --short HEAD)'","git_branch":"'$(git rev-parse --abbrev-ref HEAD)'","built_at":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}' > voxbulk-api/build_info.json
   ./vox.sh restart

2. Wrong Yallasay profile (phone number in profile field):
   Admin → Telnyx → clear Yallasay messaging profile ID → Apply Telnyx setup → Save

3. No inbound webhooks for 099:
   Telnyx portal → Messaging → WhatsApp → WABA → link +447822002099
   Webhook: https://api.voxbulk.com/telnyx/webhooks/messages
EOF

if [[ "$FOLLOW" -eq 1 ]]; then
  section "Live trace (Ctrl+C to stop) — send WhatsApp to +447822002099 now"
  if [[ -x "$ROOT/scripts/vps-abuu-live-trace.sh" ]]; then
    exec bash "$ROOT/scripts/vps-abuu-live-trace.sh"
  else
    tail -f "$API_LOG" | grep -E --line-buffered 'yallasay_inbound|abuu_wa_trace|abuu_live_trace|abuu_wa_reply_failed'
  fi
fi

echo ""
echo "Done. Copy this full output if still broken."
