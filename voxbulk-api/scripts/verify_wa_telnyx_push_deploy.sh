#!/usr/bin/env bash
# Verify VPS has the Telnyx push fix deployed and a template prepares a valid Meta BODY example.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT/.." && pwd)"
TEMPLATE_NAME="${1:-voxbulk_survey_food_quality_hospitality_food_food_quality_rating}"

echo "=== VoxBulk WA Telnyx push deploy check ==="
if [[ -d "$REPO_ROOT/.git" ]]; then
  echo "Git branch: $(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  echo "Git commit: $(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  git -C "$REPO_ROOT" log -1 --oneline 2>/dev/null || true
else
  echo "Git: not a repo at $REPO_ROOT"
fi
echo ""

cd "$ROOT"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "ERROR: missing $ROOT/.venv — create venv and install requirements first." >&2
  exit 1
fi

echo "Diagnose template: $TEMPLATE_NAME"
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/diagnose_wa_template_push.py" --template-name "$TEMPLATE_NAME"
