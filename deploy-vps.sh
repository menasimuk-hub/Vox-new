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
#   VOX_GIT_BRANCH=main               branch to pull (default: main — production)
#   VOX_HARD_RESET=1               discard local edits and reset to remote branch
#   VOX_SKIP_GIT=1                 skip git pull (deploy current tree only)
#   VOX_SKIP_BUILD=1               skip npm build (API + migrate only — UI will stay stale!)
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

# shellcheck source=scripts/lib/vps-git-sync.sh
source "$ROOT/scripts/lib/vps-git-sync.sh"

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
  info "Syncing git → $GIT_REMOTE/$GIT_BRANCH (checkout + ff-only pull) …"
  local remote_sha
  remote_sha=$(git -C "$ROOT" ls-remote "$GIT_REMOTE" "refs/heads/$GIT_BRANCH" 2>/dev/null | awk '{print $1}' | head -1)
  if [[ -n "$remote_sha" ]]; then
    info "GitHub $GIT_BRANCH tip: ${remote_sha:0:7}"
  else
    warn "Could not read remote SHA for $GIT_REMOTE/$GIT_BRANCH — check network and branch name"
  fi
  _clear_untracked_pull_conflicts
  VOX_GIT_BRANCH="$GIT_BRANCH" vox_git_sync "$ROOT" || fail "git sync failed — try: VOX_HARD_RESET=1 VOX_GIT_BRANCH=$GIT_BRANCH ./deploy-vps.sh"
  chmod +x "$ROOT/scripts/run-celery-worker.sh" "$ROOT/scripts/run-celery-beat.sh" 2>/dev/null || true
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
    warn "VOX_SKIP_BUILD=1 — skipping frontend builds (admin, dashboard, public will NOT update)"
    return
  fi
  sync_brand_assets
  info "Building all web apps: admin + dashboard + public (when present) …"
  build_frontend "$ADMIN_DIR" "admin (adim-web)"
  build_frontend "$DASH_DIR" "dashboard"
  if [[ -d "$PUBLIC_DIR" ]]; then
    build_frontend "$PUBLIC_DIR" "public site"
  else
    warn "Public frontend not found at $PUBLIC_DIR — skip"
  fi
}

sync_brand_assets() {
  local script="$ROOT/scripts/sync-brand-assets.mjs"
  if [[ ! -f "$script" ]]; then
    warn "Brand sync script missing: $script"
    return
  fi
  check_cmd node
  info "Syncing brand logos (voxbulk-api/logos → admin, dashboard, frontpage) …"
  node "$script"
}

copy_dist() {
  local src="$1"
  local dest="$2"
  local label="$3"
  if [[ -z "$dest" ]]; then
    return
  fi
  [[ -d "$src" ]] || fail "$label dist missing: $src (build failed?)"
  [[ -f "$src/index.html" ]] || fail "$label build invalid: missing $src/index.html"
  local asset_count
  asset_count=$(find "$src" -maxdepth 2 -type f \( -name '*.js' -o -name '*.css' \) 2>/dev/null | wc -l | tr -d ' ')
  [[ "${asset_count:-0}" -gt 0 ]] || fail "$label build invalid: no JS/CSS assets under $src"

  if [[ -d "$dest" && -f "$dest/index.html" ]]; then
    local backup="${dest}.backup-$(date +%Y%m%d-%H%M%S)"
    info "Backing up $label wwwroot → $backup"
    sudo cp -a "$dest" "$backup" || warn "Could not backup $dest"
    local safe_label
    safe_label=$(printf '%s' "$label" | tr -c 'a-zA-Z0-9._-' '-')
    # Best-effort only — never abort deploy if /tmp marker is not writable
    echo "$backup" > "/tmp/voxbulk-backup-${safe_label}.path" 2>/dev/null || true
  fi

  info "Copying $label → $dest"
  sudo mkdir -p "$dest"
  sudo rsync -a --delete --exclude='.user.ini' "$src/" "$dest/"
}

verify_api_import() {
  info "Preflight: verifying API imports …"
  cd "$API_DIR"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  # Do not pipe to tee here: tee permission errors were misreported as import failures.
  if ! python -c "import main"; then
    fail "API import failed — uvicorn will not start. Fix Python errors before restarting services."
  fi
  info "API import OK"
}

require_api_health() {
  local attempts="${1:-30}"
  local i=0
  info "Waiting for API /health (up to ${attempts}s) …"
  while (( i < attempts )); do
    if curl -sf -H "Host: api.voxbulk.com" http://127.0.0.1:8000/health >/dev/null 2>&1; then
      info "API health OK on 127.0.0.1:8000"
      return 0
    fi
    if curl -sf -H "Host: 127.0.0.1" http://127.0.0.1:8000/health >/dev/null 2>&1; then
      info "API health OK on 127.0.0.1:8000"
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  warn "API health check failed — tail of $API_LOG:"
  tail -n 30 /tmp/voxbulk-api.log 2>/dev/null || true
  fail "API did not respond on /health after restart. Run: bash scripts/vps-recover-api.sh"
}

nginx_test_if_present() {
  if command -v nginx >/dev/null 2>&1; then
    info "Running nginx -t …"
    sudo nginx -t || fail "nginx -t failed — fix nginx config before reloading"
  fi
}

sync_well_known() {
  local src="$PUBLIC_DIR/public/.well-known"
  local dest="${VOX_PUBLIC_DIST}/.well-known"
  if [[ ! -d "$src" ]]; then
    return 0
  fi
  info "Syncing .well-known verification files → $dest"
  sudo mkdir -p "$dest"
  sudo rsync -a "$src/" "$dest/"
}

deploy_static() {
  copy_dist "$ADMIN_DIR/dist" "${VOX_ADMIN_DIST:-}" "admin"
  copy_dist "$DASH_DIR/dist/client" "${VOX_DASH_DIST:-}" "dashboard-dist-client"
  sync_well_known
  # Public site (TanStack Start) is served via vite preview :5173 — NOT static wwwroot.
}

restart_services() {
  nginx_test_if_present
  verify_api_import
  ensure_auth_url_env
  info "Restarting API + public preview (+ Celery if configured in supervisor) …"
  bash "$VOX_SH" restart
  require_api_health 30
}

ensure_auth_url_env() {
  local env_file="$API_DIR/.env"
  [[ -f "$env_file" ]] || return 0

  set_env_flag() {
    local key="$1" val="$2"
    if grep -q "^${key}=" "$env_file" 2>/dev/null; then
      if grep "^${key}=" "$env_file" | grep -qE 'localhost|127\.0\.0\.1'; then
        sed -i "s|^${key}=.*|${key}=${val}|" "$env_file"
        warn "Updated $key in .env (was localhost)"
      fi
    else
      echo "${key}=${val}" >> "$env_file"
      info "Added $key to .env"
    fi
  }

  # shellcheck disable=SC1090
  source "$env_file" 2>/dev/null || true
  if [[ "${ENV:-}" == "production" || "${ENV:-}" == "prod" ]]; then
    set_env_flag PUBLIC_APP_ORIGIN "https://voxbulk.com"
    set_env_flag DASHBOARD_APP_ORIGIN "https://dashboard.voxbulk.com"
  fi

  if [[ -x "$ROOT/scripts/vps-check-auth-env.sh" ]]; then
    bash "$ROOT/scripts/vps-check-auth-env.sh" || warn "Auth URL env check failed — fix voxbulk-api/.env before OAuth/PWA login"
  fi
}

post_checks() {
  info "Post-deploy checks …"
  sleep 2
  bash "$VOX_SH" status || warn "Status check reported issues — see $DEPLOY_LOG"

  info "Verifying /health/build …"
  if curl -sf -H "Host: api.voxbulk.com" http://127.0.0.1:8000/health/build >/tmp/voxbulk-health-build.json 2>/dev/null \
    || curl -sf http://127.0.0.1:8000/health/build >/tmp/voxbulk-health-build.json 2>/dev/null; then
    python3 - <<'PY' || warn "health/build deploy_ok=false — running process may be stale"
import json
from pathlib import Path
p = Path("/tmp/voxbulk-health-build.json")
data = json.loads(p.read_text())
keys = (
    "status", "git_sha", "git_branch", "built_at", "deploy_ok",
    "boot_marker_present_on_disk", "router_marker_present_on_disk", "service_marker_present_on_disk",
    "boot_marker_loaded", "router_marker_loaded", "service_marker_loaded",
    "boot_marker_executed_in_process", "webhook_build_marker",
)
print("health/build:", json.dumps({k: data.get(k) for k in keys}, indent=2))
if data.get("wa_survey_debug_markers") is not None:
    raise SystemExit("stale /health/build handler — wa_survey_debug_markers should not exist")
if not data.get("deploy_ok"):
    raise SystemExit(1)
PY
  else
    warn "Could not curl /health/build — API may not be running"
  fi

  if [[ -x "$ROOT/scripts/vps-verify-deploy.sh" ]]; then
    bash "$ROOT/scripts/vps-verify-deploy.sh" || warn "vps-verify-deploy.sh reported issues"
  fi

  if [[ -d "${VOX_DASH_DIST:-}" ]]; then
    local dash_js
    dash_js=$(grep -oE '/assets/[^"]+\.js' "$VOX_DASH_DIST/index.html" 2>/dev/null | head -1 || true)
    if [[ -n "$dash_js" && -f "$VOX_DASH_DIST${dash_js}" ]]; then
      if grep -q 'tabler-icons' "$VOX_DASH_DIST/index.html" 2>/dev/null; then
        fail "Dashboard wwwroot still OLD theme (tabler-icons) — rebuild and rsync dist/client/"
      else
        info "  Dashboard static OK: index.html → $dash_js (new UI)"
      fi
    else
      warn "  Dashboard wwwroot: could not verify index.html asset bundle (check $VOX_DASH_DIST after rsync)"
    fi
    if [[ -f "$VOX_DASH_DIST/build-info.json" ]]; then
      vox_verify_build_info_sha "$ROOT" "$VOX_DASH_DIST" "dashboard" || fail "Dashboard build-info SHA mismatch — deploy did not publish current commit"
      info "  Dashboard build-info.json:"
      cat "$VOX_DASH_DIST/build-info.json"
    else
      fail "Missing $VOX_DASH_DIST/build-info.json — npm prebuild sync:build-info did not run"
    fi
  fi

  local ms_well_known="${VOX_PUBLIC_DIST}/.well-known/microsoft-identity-association.json"
  if [[ -f "$ms_well_known" ]]; then
    info "  Microsoft publisher domain file on disk: $ms_well_known"
    local ms_code
    ms_code=$(curl -s -o /dev/null -w "%{http_code}" -H "Host: voxbulk.com" \
      "http://127.0.0.1/.well-known/microsoft-identity-association.json" 2>/dev/null || echo "000")
    if [[ "$ms_code" == "200" ]]; then
      info "  https://voxbulk.com/.well-known/microsoft-identity-association.json → HTTP 200"
    else
      warn "  Microsoft identity file HTTP $ms_code via nginx (want 200)."
      warn "  Update nginx: replace 'location ~ \\.well-known' with alias block in docs/nginx-voxbulk.com.conf, then: sudo nginx -t && sudo nginx -s reload"
    fi
  else
    warn "  Missing $ms_well_known — run deploy after pulling microsoft-identity-association.json"
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
    if [[ -f "$VOX_ADMIN_DIST/build-info.json" ]]; then
      vox_verify_build_info_sha "$ROOT" "$VOX_ADMIN_DIST" "admin" || fail "Admin build-info SHA mismatch — deploy did not publish current commit"
      info "  Admin build-info.json:"
      cat "$VOX_ADMIN_DIST/build-info.json"
    else
      fail "Missing $VOX_ADMIN_DIST/build-info.json — npm prebuild sync:build-info did not run"
    fi
    local health_code
    health_code=$(curl -s -o /dev/null -w "%{http_code}" https://admin.voxbulk.com/health 2>/dev/null || echo "000")
    info "  https://admin.voxbulk.com/health → HTTP $health_code (want 200)"
  fi

  # New routes added in recent releases
  info "Verifying billing invoice lifecycle routes (expect 401/403, not 404) …"
  for path in \
    "/admin/billing/invoices/00000000-0000-0000-0000-000000000001/void" \
    "/admin/billing/invoices/00000000-0000-0000-0000-000000000001"
  do
    code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Host: api.voxbulk.com" -H "Content-Type: application/json" -d '{"reason":"deploy-check"}' "http://127.0.0.1:8000${path}" 2>/dev/null || echo "000")
    if [[ "$code" == "404" ]]; then
      fail "Billing route missing ($code): POST $path — API not restarted after pull. Run: cd $ROOT && ./vox.sh restart"
    else
      info "  Route registered ($code): POST $path"
    fi
  done

  local checks=(
    "/health"
    "/public/brand"
    "/public/brand/logo-black"
    "/admin/ai-team/dashboard"
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

5. Brand logos: replace files in voxbulk-api/logos/ — deploy runs sync-brand-assets.mjs before every frontend build.

6. Microsoft Entra publisher domain (voxbulk.com):
   - File: /.well-known/microsoft-identity-association.json
   - Deploy syncs it to /www/wwwroot/voxbulk.com/.well-known/
   - nginx must serve that path (NOT the old "location ~ \.well-known { allow all; }" block — it 404s).
   - One-time: bash scripts/vps-install-microsoft-well-known-nginx.sh
   - Or replace vhost using docs/nginx-voxbulk.com.conf, then: sudo nginx -t && sudo nginx -s reload

7. Invoice PDF styling requires WeasyPrint system libraries on Linux:
   sudo apt-get install -y libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info libcairo2
   Then: pip install -r voxbulk-api/requirements.txt && ./vox.sh restart

Known problems to watch:
- Canonical GitHub repo: menasimuk-hub/Vox-new only (not menasimuk-hub/Vox)
- Port 8000 already in use → ./vox.sh stop before deploy
- SQLite vs MySQL: set DATABASE_URL in voxbulk-api/.env before migrate

Legacy product removal (one-time on upgraded VPS):
- Remove obsolete isolated-product env vars from voxbulk-api/.env
- Re-save Telnyx in Admin → Integrations (clears legacy second-line keys from stored config)
- Optional: disable unused restaurant/driver nginx vhosts; drop isolated MySQL DB when ready
NOTES
}

write_build_info() {
  cd "$ROOT"
  local sha branch
  sha=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
  branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
  cat > "$API_DIR/build_info.json" <<EOF
{"git_sha":"$sha","git_branch":"$branch","built_at":"$(date -u +"%Y-%m-%dT%H:%M:%SZ")"}
EOF
  info "Wrote build_info.json ($branch @ $sha)"
}

main() {
  exec > >(tee -a "$DEPLOY_LOG") 2>&1
  info "VOXBULK deploy started $(date -Iseconds)"
  info "Log: $DEPLOY_LOG"
  info "Target branch: $GIT_BRANCH"
  preflight
  git_pull
  write_build_info
  api_deps_and_migrate
  verify_api_import
  build_all_frontends
  deploy_static
  restart_services
  post_checks
  print_notes
  vox_print_deploy_banner COMPLETE "$ROOT"
}

main "$@"
