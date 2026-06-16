#!/usr/bin/env bash
# Simulate inbound Yallasay WhatsApp and print route + Abuu trace (no phone needed).
#
# Usage:
#   cd /www/voxbulk
#   bash scripts/vps-yallasay-e2e-trace.sh
#   bash scripts/vps-yallasay-e2e-trace.sh --omit-to
#   bash scripts/vps-yallasay-e2e-trace.sh --preflight
#   bash scripts/vps-yallasay-e2e-trace.sh --follow
#
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$ROOT/voxbulk-api"
API_LOG="${VOX_API_LOG:-/tmp/voxbulk-api.log}"
FOLLOW=0
EXTRA_ARGS=()

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

section() { echo -e "\n${GREEN}=== $* ===${NC}"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*" >&2; }
fail() { echo -e "${RED}[fail]${NC} $*" >&2; }

usage() {
  cat <<'EOF'
Usage: bash scripts/vps-yallasay-e2e-trace.sh [options]

  (default)     simulate inbound "Yallasay" + print route/log/DB trace
  --omit-to     simulate Telnyx webhook without `to` (profile inference path)
  --preflight   config checks only, no simulate
  --route-only  pass when route + Abuu OK (ignore Telnyx outbound on fake probe number)
  --follow      after simulate, tail live Abuu trace (Ctrl+C to stop)
  --text TEXT   inbound message text (default: Yallasay)
  --from PHONE  simulated customer E.164 (default: +447700900123)
  -h, --help    this help

Env: VOX_API_LOG, VOXBULK_API_BASE_URL
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --follow|-f)
      FOLLOW=1
      shift
      ;;
    --preflight)
      EXTRA_ARGS+=(--preflight)
      shift
      ;;
    --route-only)
      EXTRA_ARGS+=(--route-only)
      shift
      ;;
    --omit-to)
      EXTRA_ARGS+=(--omit-to)
      shift
      ;;
    --text)
      EXTRA_ARGS+=(--text "$2")
      shift 2
      ;;
    --from)
      EXTRA_ARGS+=(--from "$2")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      warn "Unknown arg: $1 (pass --help for usage)"
      shift
      ;;
  esac
done

section "Yallasay E2E trace"
if [[ ! -d "$API_DIR/.venv" ]]; then
  fail "Missing $API_DIR/.venv — run deploy first"
  exit 1
fi

# shellcheck disable=SC1091
source "$API_DIR/.venv/bin/activate"
cd "$API_DIR"

export VOX_API_LOG="$API_LOG"
set +e
python3 scripts/yallasay_e2e_trace.py --log "$API_LOG" "${EXTRA_ARGS[@]}"
EXIT_CODE=$?
set -e

if [[ "$FOLLOW" -eq 1 && "$EXIT_CODE" -ne 1 ]]; then
  section "Live trace (send real WhatsApp to +447822002099 to compare)"
  bash "$ROOT/scripts/vps-abuu-live-trace.sh" --log "$API_LOG"
fi

exit "$EXIT_CODE"
