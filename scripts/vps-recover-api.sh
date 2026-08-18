#!/usr/bin/env bash
# Run ON THE VPS via Baota/aaPanel terminal or provider console when API is down (502).
# Recovers A then B sequentially — never stops both gunicorn units at once.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$ROOT/voxbulk-api"
API_LOG="/tmp/voxbulk-api.log"
API_B_LOG="/tmp/voxbulk-api-b.log"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[recover]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*" >&2; }
fail()  { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }

_sys() {
  if [[ "$(id -u)" -eq 0 ]]; then
    systemctl "$@"
    return $?
  fi
  if command -v sudo >/dev/null 2>&1; then
    sudo -n systemctl "$@" 2>/dev/null && return 0
    sudo systemctl "$@"
    return $?
  fi
  systemctl "$@"
}

_health() {
  local port="$1"
  curl -sf -H "Host: api.voxbulk.com" "http://127.0.0.1:${port}/health" >/dev/null 2>&1 \
    || curl -sf -H "Host: 127.0.0.1" "http://127.0.0.1:${port}/health" >/dev/null 2>&1
}

_wait_health() {
  local port="$1" seconds="${2:-30}"
  local i
  for i in $(seq 1 "$seconds"); do
    if _health "$port"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

info "VOXBULK API recovery — $(date -Iseconds)"
info "Repo: $ROOT"

[[ -d "$API_DIR" ]] || fail "API dir missing: $API_DIR"

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

info "Step 2: sequential restart (A :8000 first, B :8001 only after A is healthy)"
if [[ -f /etc/systemd/system/voxbulk-api.service ]]; then
  info "systemctl restart voxbulk-api (:8000) — B stays up"
  _sys restart voxbulk-api.service || warn "systemctl restart A failed"
  _sys --no-pager --full status voxbulk-api.service 2>/dev/null | head -n 15 || true
else
  fail "Missing voxbulk-api.service — sudo bash scripts/vps-setup-api-systemd.sh"
fi

info "Step 3: wait for API A /health"
if _wait_health 8000 30; then
  info "API A healthy"
  curl -sf -H "Host: api.voxbulk.com" http://127.0.0.1:8000/health 2>/dev/null \
    || curl -sf -H "Host: 127.0.0.1" http://127.0.0.1:8000/health
  echo
else
  warn "API A still not healthy after 30s"
  _sys --no-pager --full status voxbulk-api.service 2>/dev/null | head -n 25 || true
  if [[ -f "$API_LOG" ]]; then
    echo "--- tail $API_LOG ---"
    tail -n 40 "$API_LOG"
  fi
  fail "Recovery incomplete — A did not come up. Do not restart B until A is healthy."
fi

if [[ -f /etc/systemd/system/voxbulk-api-b.service ]]; then
  info "Step 4: systemctl restart voxbulk-api-b (:8001) — A stays up"
  _sys restart voxbulk-api-b.service || warn "systemctl restart B failed"
  if _wait_health 8001 30; then
    info "API B healthy"
    curl -sf -H "Host: api.voxbulk.com" http://127.0.0.1:8001/health 2>/dev/null \
      || curl -sf -H "Host: 127.0.0.1" http://127.0.0.1:8001/health
    echo
  else
    warn "API B not healthy — nginx will skip :8001 (max_fails) until it recovers"
    if [[ -f "$API_B_LOG" ]]; then
      tail -n 20 "$API_B_LOG" || true
    fi
  fi
else
  warn "voxbulk-api-b.service missing — sudo bash scripts/vps-setup-api-systemd.sh"
fi

info "Recovery complete. Smoke: curl -s https://api.voxbulk.com/health"
