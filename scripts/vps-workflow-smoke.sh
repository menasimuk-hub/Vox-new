#!/usr/bin/env bash
# Workflow smoke — API routes, welcome email readiness, UI pages, optional auth/register tests.
# Usage:
#   cd /www/voxbulk && bash scripts/vps-workflow-smoke.sh
#   VOXBULK_EMAIL=... VOXBULK_PASSWORD=... bash scripts/vps-workflow-smoke.sh --check-auth
#   bash scripts/vps-workflow-smoke.sh --test-register
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$ROOT/voxbulk-api"

if [[ -x "$API_DIR/.venv/bin/python3" ]]; then
  PYTHON="$API_DIR/.venv/bin/python3"
else
  PYTHON="python3"
fi

cd "$API_DIR"
exec "$PYTHON" scripts/workflow_smoke_test.py "$@"
