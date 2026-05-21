#!/usr/bin/env bash
# VOXBULK VPS — pull latest code, migrate DB, build frontends, restart services
#
# Usage (on VPS):
#   cd /path/to/Vox   # repo root (same folder as vox.sh)
#   chmod +x deploy-vps.sh vox.sh
#   ./deploy-vps.sh
#
# Optional env overrides:
#   VOX_GIT_REMOTE=voxnew          git remote name (default: origin)
#   VOX_GIT_BRANCH=main            branch to pull
#   VOX_SKIP_GIT=1                 skip git pull (deploy current tree only)
#   VOX_SKIP_BUILD=1               skip npm build (API + migrate only)
#   VOX_SKIP_MIGRATE=1             skip alembic upgrade
#   VOX_ADMIN_DIST=/var/www/admin  copy admin build here (if set)
#   VOX_DASH_DIST=/var/www/dashboard
#   VOX_PUBLIC_DIST=/var/www/voxbulk
#
set -euo pipefail

VOX_ADMIN_DIST="${VOX_ADMIN_DIST:-/www/wwwroot/admin.voxbulk.com}"
VOX_DASH_DIST="${VOX_DASH_DIST:-/www/wwwroot/dashboard.voxbulk.com}"
VOX_PUBLIC_DIST="${VOX_PUBLIC_DIST:-/www/wwwroot/voxbulk.com}"

ROOT="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$ROOT/voxbulk-api"
ADMIN_DIR="$ROOT/admin.voxbulk.com/adim-web"
DASH_DIR="$ROOT/dashboard.voxbulk.com/dashboard-web"
PUBLIC_DIR="$ROOT/voxbulk.com/frontend"
VOX_SH="$ROOT/vox.sh"

GIT_REMOTE="${VOX_GIT_REMOTE:-origin}"
GIT_BRANCH="${VOX_GIT_BRANCH:-main}"
DEPLOY_LOG="${VOX_DEPLOY_LOG:-/tmp/voxbulk-deploy.log}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*" >&2; }
fail()  { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }

check_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing command: $1"
}

preflight() {
  check_cmd git
  check_cmd python3
  check_cmd npm
  check_cmd curl
  [[ -d "$API_DIR" ]] || fail "API dir not found: $API_DIR"
  [[ -f "$API_DIR/main.py" ]] || fail "main.py missing — wrong repo root?"
  [[ -f "$VOX_SH" ]] || fail "vox.sh missing at $VOX_SH"
}

git_pull() {
  if [[ "${VOX_SKIP_GIT:-0}" == "1" ]]; then
    warn "VOX_SKIP_GIT=1 — skipping git pull"
    return
  fi
  info "Pulling $GIT_REMOTE/$GIT_BRANCH …"
  cd "$ROOT"
  git fetch "$GIT_REMOTE" "$GIT_BRANCH"
  # Prefer merge; if unrelated histories, warn and stop (do not force)
  if ! git merge-base "HEAD" "$GIT_REMOTE/$GIT_BRANCH" >/dev/null 2>&1; then
    fail "Git histories unrelated. On VPS run: git fetch $GIT_REMOTE && git reset --hard $GIT_REMOTE/$GIT_BRANCH (only if you accept overwriting local VPS changes)"
  fi
  git pull --ff-only "$GIT_REMOTE" "$GIT_BRANCH" || fail "git pull failed — commit or stash local VPS changes first"
}

api_deps_and_migrate() {
  info "Python venv + dependencies …"
  cd "$API_DIR"
  if [[ ! -d .venv ]]; then
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -q -U pip
  pip install -q -r requirements.txt

  if [[ "${VOX_SKIP_MIGRATE:-0}" == "1" ]]; then
    warn "VOX_SKIP_MIGRATE=1 — skipping alembic"
    return
  fi

  info "Running database migrations (0046 messaging, 0047 email HTML, 0048 KB scope) …"
  python -m alembic upgrade head
  info "Migration OK"
}

build_frontend() {
  local dir="$1"
  local name="$2"
  info "Building $name …"
  cd "$dir"
  if [[ ! -d node_modules ]]; then
    npm ci || npm install
  else
    npm install
  fi
  npm run build
}

build_all_frontends() {
  if [[ "${VOX_SKIP_BUILD:-0}" == "1" ]]; then
    warn "VOX_SKIP_BUILD=1 — skipping frontend builds"
    return
  fi
  build_frontend "$ADMIN_DIR" "admin (adim-web)"
  build_frontend "$DASH_DIR" "dashboard"
  if [[ -d "$PUBLIC_DIR" ]]; then
    build_frontend "$PUBLIC_DIR" "public site"
  else
    warn "Public frontend not found at $PUBLIC_DIR — skip"
  fi
}

copy_dist() {
  local src="$1"
  local dest="$2"
  local label="$3"
  if [[ -z "$dest" ]]; then
    return
  fi
  [[ -d "$src" ]] || fail "$label dist missing: $src (build failed?)"
  info "Copying $label → $dest"
  sudo mkdir -p "$dest"
  sudo rsync -a --delete --exclude='.user.ini' "$src/" "$dest/"
}

deploy_static() {
  copy_dist "$ADMIN_DIR/dist" "${VOX_ADMIN_DIST:-}" "admin"
  copy_dist "$DASH_DIR/dist" "${VOX_DASH_DIST:-}" "dashboard"
  # Public site (TanStack Start) is served via vite preview :5173 — NOT static wwwroot.
}

restart_services() {
  info "Restarting API + public preview …"
  bash "$VOX_SH" restart
}

post_checks() {
  info "Post-deploy checks …"
  sleep 2
  bash "$VOX_SH" status || warn "Status check reported issues — see $DEPLOY_LOG"

  if [[ -d "${VOX_ADMIN_DIST:-}" ]]; then
    local js
    js=$(grep -oE '/assets/[^"]+\.js' "$VOX_ADMIN_DIST/index.html" 2>/dev/null | head -1 || true)
    if [[ -n "$js" && -f "$VOX_ADMIN_DIST${js}" ]]; then
      info "  Admin static OK: index.html → $js exists in wwwroot"
    else
      warn "  Admin wwwroot broken: index.html JS ($js) missing — browser will show blank page"
      warn "  Fix: cd $ADMIN_DIR && npm run build && rsync dist/ → $VOX_ADMIN_DIST"
    fi
    local health_code
    health_code=$(curl -s -o /dev/null -w "%{http_code}" https://admin.voxbulk.com/health 2>/dev/null || echo "000")
    info "  https://admin.voxbulk.com/health → HTTP $health_code (want 200)"
  fi

  # New routes added in recent releases
  local checks=(
    "/health"
    "/admin/knowledge-base?scope=lead"
    "/admin/messaging/whatsapp/templates"
    "/admin/email/templates"
  )
  for path in "${checks[@]}"; do
    if curl -sf -o /dev/null -H "Host: api.voxbulk.com" "http://127.0.0.1:8000${path}" 2>/dev/null; then
      info "  OK $path (no auth — expected 401/403 without token is also fine if route exists)"
    else
      code=$(curl -s -o /dev/null -w "%{http_code}" -H "Host: api.voxbulk.com" "http://127.0.0.1:8000${path}" 2>/dev/null || echo "000")
      if [[ "$code" == "401" || "$code" == "403" || "$code" == "404" ]]; then
        if [[ "$code" == "404" ]]; then
          warn "  Route 404: $path — restart API if code was just pulled"
        else
          info "  Route exists ($code): $path"
        fi
      else
        warn "  Check failed ($code): $path"
      fi
    fi
  done
}

print_notes() {
  cat <<'NOTES'

══════════════════════════════════════════════════════════════
After deploy — manual checks
══════════════════════════════════════════════════════════════
1. Admin → Marketing → Front page call leads
   - Upload lead-scoped .md files (scope=lead)
   - Save settings → Telnyx sync

2. Admin → Marketing → Sales setup
   - Upload sales-scoped .md files (scope=sales)

3. Admin → Settings → Email templates
   - Requires migrations 0046/0047; restart API if 404

4. Re-tag old KB files if they show under wrong agent:
   - Re-upload on correct page, or SQL: UPDATE knowledge_base_files SET scope='lead'|sales'|org'

5. Telnyx / SMTP secrets live in .env — never commit them.

Known problems to watch:
- origin vs voxnew remotes may differ; VPS should track voxnew/main
- Unrelated git history on origin/main — use voxnew or reset --hard once
- Port 8000 already in use → ./vox.sh stop before deploy
- SQLite vs MySQL: set DATABASE_URL in voxbulk-api/.env before migrate
NOTES
}

main() {
  exec > >(tee -a "$DEPLOY_LOG") 2>&1
  info "VOXBULK deploy started $(date -Iseconds)"
  info "Log: $DEPLOY_LOG"
  preflight
  git_pull
  api_deps_and_migrate
  build_all_frontends
  deploy_static
  restart_services
  post_checks
  print_notes
  info "Deploy finished OK"
}

main "$@"
