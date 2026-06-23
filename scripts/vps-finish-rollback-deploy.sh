#!/usr/bin/env bash
# Finish rollback deploy after Alembic 0134 blocker (run on VPS as deploy user).
#
# Usage:
#   cd /www/voxbulk
#   chmod +x scripts/vps-finish-rollback-deploy.sh
#   ./scripts/vps-finish-rollback-deploy.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$ROOT/voxbulk-api"

echo "[finish-deploy] git pull origin main (need eaa868b+ with restored 0132-0134 migrations)"
git -C "$ROOT" pull origin main

cd "$API_DIR"
# shellcheck disable=SC1091
source .venv/bin/activate

echo "[finish-deploy] alembic current (expect 0134_survey_type_customer_hidden on production DB)"
python -m alembic current || {
  echo "[finish-deploy] If 'Can't locate revision 0134': repo is stale — git pull again"
  echo "[finish-deploy] Fallback: python -m alembic stamp 0131_appointment_calendar_post_survey"
  exit 1
}

echo "[finish-deploy] alembic upgrade head"
python -m alembic upgrade head

cd "$ROOT"
echo "[finish-deploy] full deploy (build + rsync + API restart)"
./deploy-vps.sh

echo "[finish-deploy] verify dashboard build-info"
cat /www/wwwroot/dashboard.voxbulk.com/build-info.json

echo "[finish-deploy] verify API health/build"
curl -sf http://127.0.0.1:8000/health/build | python3 -m json.tool | head -20

echo "[finish-deploy] optional template repair"
cd "$API_DIR"
python scripts/repair_unblock_wa_templates.py --dry-run
python scripts/repair_unblock_wa_templates.py

echo "[finish-deploy] done — hard-refresh dashboard and retest Surveys Step 2"
