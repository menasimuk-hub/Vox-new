#!/usr/bin/env bash
# Phase 1 rollout prep on VPS — run from repo root (/www/voxbulk).
# Usage:
#   ./voxbulk-api/scripts/vps_phase1_rollout_prep.sh off   # Section 0 baseline
#   ./voxbulk-api/scripts/vps_phase1_rollout_prep.sh on    # Section 1 enable
#   ./voxbulk-api/scripts/vps_phase1_rollout_prep.sh status

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="$ROOT/voxbulk-api/.env"
BRANCH="${VOX_GIT_BRANCH:-feat/dashboard-ai-assistant-v1}"

set_flag() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
  else
    echo "${key}=${val}" >> "$ENV_FILE"
  fi
}

pull_branch() {
  cd "$ROOT"
  git fetch origin "$BRANCH"
  git checkout "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH" "origin/$BRANCH"
  git pull origin "$BRANCH"
}

apply_off() {
  set_flag ABUU_AGENT_PHASE1_ORCHESTRATION false
  set_flag ABUU_AGENT_WAITER_MODE false
  set_flag ABUU_VOICE_ORDER_DEBUG true
  set_flag ABUU_CONVERSATION_MODE agent
}

apply_on() {
  set_flag ABUU_AGENT_PHASE1_ORCHESTRATION true
  set_flag ABUU_AGENT_WAITER_MODE false
  set_flag ABUU_VOICE_ORDER_DEBUG true
  set_flag ABUU_CONVERSATION_MODE agent
}

status() {
  echo "=== Branch ==="
  cd "$ROOT" && git log -1 --oneline
  echo "=== Phase 1 env ==="
  grep -E 'ABUU_AGENT_PHASE1|ABUU_AGENT_WAITER|ABUU_VOICE_ORDER_DEBUG|ABUU_CONVERSATION_MODE' "$ENV_FILE" || true
  echo "=== Latest debug id ==="
  cd "$ROOT/voxbulk-api" && source .venv/bin/activate
  python3 scripts/abuu_voice_order_debug.py latest 2>/dev/null || echo "none"
}

case "${1:-status}" in
  off)
    pull_branch
    apply_off
    cd "$ROOT" && ./vox.sh restart
    status
    echo "Send baseline voice: وجبات سريعة، ايش المنيو تاع الوجبات السريعة؟"
    echo "Then: python3 scripts/abuu_voice_order_debug.py latest"
    ;;
  on)
    pull_branch
    apply_on
    cd "$ROOT" && ./vox.sh restart
    status
    echo "Run 5 voice tests per voxbulk-api/docs/phase1-rollout-runbook.md"
    ;;
  status)
    status
    ;;
  *)
    echo "Usage: $0 {off|on|status}" >&2
    exit 1
    ;;
esac
