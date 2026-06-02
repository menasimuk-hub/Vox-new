#!/usr/bin/env bash
# VOXBULK VPS — pull latest code, migrate DB, build frontends, restart services
#
# Usage (on VPS):
#   cd /path/to/Vox   # repo root (same folder as vox.sh)
#   chmod +x deploy-vps.sh vox.sh
#   ./deploy-vps.sh
#
# Optional env overrides:
#   VOX_GIT_REMOTE=origin           git remote name (default: origin → menasimuk-hub/Vox-new)
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

_clear_untracked_pull_conflicts() {
  local remote_ref="$GIT_REMOTE/$GIT_BRANCH"
  local prefix path
  local prefixes=(
    voxbulk-api/logos
    admin.voxbulk.com/adim-web/public/brand
    dashboard.voxbulk.com/dashboard-web/public/brand
    voxbulk.com/frontend/public/brand
  )
  for prefix in "${prefixes[@]}"; do
    while IFS= read -r path; do
      [[ -n "$path" ]] || continue
      if [[ -f "$path" ]] && ! git ls-files --error-unmatch "$path" >/dev/null 2>&1; then
        warn "Removing untracked $path (now tracked in git) so pull can proceed"
        rm -f "$path"
      fi
    done < <(git ls-tree -r --name-only "$remote_ref" -- "$prefix" 2>/dev/null || true)
  done
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
  if ! git diff --quiet deploy-vps.sh vox.sh 2>/dev/null; then
    warn "Local edits to deploy-vps.sh or vox.sh — resetting so git pull can proceed"
    git checkout -- deploy-vps.sh vox.sh
  fi
  if ! git diff --quiet && [[ "${VOX_FORCE_PULL:-0}" == "1" ]]; then
    warn "VOX_FORCE_PULL=1 — stashing other local changes before pull"
    git stash push -u -m "voxbulk-deploy-auto-stash $(date -Iseconds)"
  fi
  _clear_untracked_pull_conflicts
  if ! git pull --ff-only "$GIT_REMOTE" "$GIT_BRANCH"; then
    if [[ "${VOX_FORCE_PULL:-0}" == "1" ]]; then
      warn "VOX_FORCE_PULL=1 — stashing all local/untracked changes and retrying pull"
      git stash push -u -m "voxbulk-deploy-force-pull $(date -Iseconds)" || true
      _clear_untracked_pull_conflicts
      git pull --ff-only "$GIT_REMOTE" "$GIT_BRANCH" || fail "git pull failed after stash — run: git status; git reset --hard $GIT_REMOTE/$GIT_BRANCH"
    else
      fail "git pull failed — remove untracked brand/logo files blocking merge, or run: VOX_FORCE_PULL=1 ./deploy-vps.sh"
    fi
  fi
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

  if [[ "$(uname -s)" == "Linux" ]]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
    if ! python -c "from weasyprint import HTML" 2>/dev/null; then
      if command -v apt-get >/dev/null 2>&1; then
        info "Installing WeasyPrint system libraries (styled invoice PDFs) …"
        sudo apt-get update -qq
        sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
          libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0 \
          libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info libcairo2 \
          || warn "apt install for WeasyPrint failed — PDF may be plain text"
      else
        warn "WeasyPrint system libraries missing — invoice PDFs may be plain text"
      fi
      if python -c "from weasyprint import HTML" 2>/dev/null; then
        info "WeasyPrint ready for invoice PDF rendering"
      else
        warn "WeasyPrint still unavailable — check apt packages above"
      fi
    fi
  fi

  if [[ "${VOX_SKIP_MIGRATE:-0}" == "1" ]]; then
    warn "VOX_SKIP_MIGRATE=1 — skipping alembic"
    return
  fi

  info "Running database migrations …"
  python -m alembic upgrade head
  python -m alembic current
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
  copy_dist "$DASH_DIR/dist/client" "${VOX_DASH_DIST:-}" "dashboard (dist/client)"
  # Public site (TanStack Start) is served via vite preview :5173 — NOT static wwwroot.
}

restart_services() {
  info "Restarting API + public preview (+ Celery if configured in supervisor) …"
  bash "$VOX_SH" restart
}

post_checks() {
  info "Post-deploy checks …"
  sleep 2
  bash "$VOX_SH" status || warn "Status check reported issues — see $DEPLOY_LOG"

  if [[ -d "${VOX_DASH_DIST:-}" ]]; then
    local dash_js
    dash_js=$(grep -oE '/assets/[^"]+\.js' "$VOX_DASH_DIST/index.html" 2>/dev/null | head -1 || true)
    if [[ -n "$dash_js" && -f "$VOX_DASH_DIST${dash_js}" ]]; then
      if grep -q 'tabler-icons' "$VOX_DASH_DIST/index.html" 2>/dev/null; then
        warn "  Dashboard wwwroot still OLD theme (tabler-icons) — rebuild and rsync dist/client/"
      else
        info "  Dashboard static OK: index.html → $dash_js (new UI)"
      fi
    else
      warn "  Dashboard wwwroot broken — run: cd dashboard-web && npm run build && rsync dist/client/ → $VOX_DASH_DIST"
    fi
  fi

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
    "/public/brand"
    "/public/brand/logo-black"
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

6. Invoice PDF styling requires WeasyPrint system libraries on Linux:
   sudo apt-get install -y libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info libcairo2
   Then: pip install -r voxbulk-api/requirements.txt && ./vox.sh restart

Known problems to watch:
- Canonical GitHub repo: menasimuk-hub/Vox-new only (not menasimuk-hub/Vox)
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
