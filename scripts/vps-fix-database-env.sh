#!/usr/bin/env bash
# Fix login 503 caused by DATABASE_URL=USER:PASS placeholder duplicates in .env
# Run ON THE VPS:  bash scripts/vps-fix-database-env.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$ROOT/voxbulk-api"
VOX_SH="$ROOT/vox.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[fix-db]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*" >&2; }
fail()  { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }

info "VOXBULK — fix DATABASE_URL / login — $(date -Iseconds)"
[[ -d "$API_DIR" ]] || fail "Missing $API_DIR"
[[ -f "$API_DIR/.env" ]] || fail "Missing $API_DIR/.env"

cd "$API_DIR"
[[ -d .venv ]] || fail "Missing .venv — run ./deploy-vps.sh first"
# shellcheck disable=SC1091
source .venv/bin/activate

info "Step 1: sanitize .env (remove USER:PASS / CHANGE_ME duplicates)"
if ! python scripts/sanitize_production_env.py --check; then
  info "Applying sanitize --write ..."
  python scripts/sanitize_production_env.py --write
else
  info ".env looks OK (no placeholder duplicates)"
fi

info "Step 2: test MySQL connection"
python -c "
from app.core.config import get_settings
from sqlalchemy import create_engine, text
e = create_engine(get_settings().database_url)
with e.connect() as c:
    print(c.execute(text('SELECT 1')).scalar())
print('DB OK')
" || fail "Database connection failed — fix DATABASE_URL in .env (aaPanel → Databases)"

info "Step 3: restart API"
bash "$VOX_SH" restart

info "Step 4: wait for /health/db"
for i in $(seq 1 30); do
  if curl -sf https://api.voxbulk.com/health/db >/dev/null 2>&1; then
    info "Database health OK"
    curl -s https://api.voxbulk.com/health/db && echo
    info "Done — retry login at admin.voxbulk.com and dashboard.voxbulk.com"
    info "Security: rotate MySQL passwords in aaPanel (credentials may have been exposed)"
    exit 0
  fi
  sleep 1
done

warn "/health/db still failing after restart"
curl -s https://api.voxbulk.com/health/db || true
echo
tail -n 30 /tmp/voxbulk-api.log 2>/dev/null || true
fail "Fix incomplete — check errors above"
