#!/usr/bin/env bash
# Run ON THE VPS via Baota/aaPanel terminal or provider console when API is down (502).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$ROOT/voxbulk-api"
VOX_SH="$ROOT/vox.sh"
API_LOG="/tmp/voxbulk-api.log"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[recover]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*" >&2; }
fail()  { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }

info "VOXBULK API recovery — $(date -Iseconds)"
info "Repo: $ROOT"

[[ -d "$API_DIR" ]] || fail "API dir missing: $API_DIR"
[[ -f "$VOX_SH" ]] || fail "vox.sh missing"

cd "$API_DIR"
if [[ ! -d .venv ]]; then
  fail "Missing voxbulk-api/.venv — run ./deploy-vps.sh first"
fi
# shellcheck disable=SC1091
source .venv/bin/activate

info "Step 1: test Python import"
if ! python -c "import main"; then
  fail "import main failed — fix syntax/import errors above, then re-run this script"
fi
info "import main OK"

info "Step 2: restart services (systemd when installed)"
if [[ -f /etc/systemd/system/voxbulk-api.service ]]; then
  info "systemctl restart voxbulk-api …"
  if [[ "$(id -u)" -eq 0 ]]; then
    systemctl restart voxbulk-api.service || true
  elif command -v sudo >/dev/null 2>&1; then
    sudo -n systemctl restart voxbulk-api.service 2>/dev/null \
      || sudo systemctl restart voxbulk-api.service || true
  fi
  systemctl --no-pager --full status voxbulk-api.service 2>/dev/null | head -n 15 || true
fi
# vox.sh prefers systemd units when present; also restarts public + Celery.
VOX_SKIP_MIGRATE=1 VOX_SKIP_DASHBOARD_PREVIEW=1 bash "$VOX_SH" restart

info "Step 3: wait for /health"
for i in $(seq 1 30); do
  if curl -sf -H "Host: api.voxbulk.com" http://127.0.0.1:8000/health >/dev/null 2>&1 \
    || curl -sf -H "Host: 127.0.0.1" http://127.0.0.1:8000/health >/dev/null 2>&1; then
    info "API healthy"
    curl -sf -H "Host: api.voxbulk.com" http://127.0.0.1:8000/health 2>/dev/null \
      || curl -sf -H "Host: 127.0.0.1" http://127.0.0.1:8000/health
    echo
    exit 0
  fi
  sleep 1
done

warn "API still not healthy after 30s"
if [[ -f /etc/systemd/system/voxbulk-api.service ]]; then
  echo "--- systemctl status voxbulk-api ---"
  systemctl --no-pager --full status voxbulk-api.service 2>/dev/null | head -n 25 || true
fi
if [[ -f "$API_LOG" ]]; then
  echo "--- tail $API_LOG ---"
  tail -n 40 "$API_LOG"
fi
fail "Recovery incomplete — check errors above. Tip: ./vox.sh install-service && ./vox.sh restart"
