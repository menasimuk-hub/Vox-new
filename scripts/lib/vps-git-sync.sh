#!/usr/bin/env bash
# Shared git sync for VPS deploy scripts.
# Usage: source this file, then call vox_git_sync "$ROOT"
#
# Env:
#   VOX_GIT_REMOTE   (default: origin)
#   VOX_GIT_BRANCH   (default: current branch, else main)
#   VOX_SKIP_GIT=1   skip fetch/checkout/pull
#   VOX_FORCE_PULL=1 stash and retry on pull failure

vox_git_sync() {
  local root="${1:?repo root required}"
  local remote="${VOX_GIT_REMOTE:-origin}"
  local branch="${VOX_GIT_BRANCH:-}"

  if [[ -z "$branch" ]]; then
    branch=$(git -C "$root" rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)
    if [[ "$branch" == "HEAD" ]]; then
      branch=main
    fi
  fi

  if [[ "${VOX_SKIP_GIT:-0}" == "1" ]]; then
    echo "[git] VOX_SKIP_GIT=1 — using tree at $(git -C "$root" rev-parse --short HEAD 2>/dev/null || echo '?')"
    return 0
  fi

  cd "$root"

  echo "[git] fetch $remote $branch"
  git fetch "$remote" "$branch"

  local remote_ref="$remote/$branch"
  if ! git rev-parse --verify "$remote_ref" >/dev/null 2>&1; then
    echo "[git] FAIL: $remote_ref not found — check branch name and GitHub push" >&2
    return 1
  fi

  echo "[git] checkout $branch"
  git checkout "$branch" 2>/dev/null || git checkout -b "$branch" "$remote_ref"

  if ! git diff --quiet deploy-vps.sh vox.sh scripts/vps-sync-dashboard.sh scripts/vps-update-ui.sh scripts/vps-sync-all-ui.sh 2>/dev/null; then
    echo "[git] Resetting local edits to deploy scripts so pull can proceed"
    git checkout -- deploy-vps.sh vox.sh scripts/vps-sync-dashboard.sh scripts/vps-update-ui.sh scripts/vps-sync-all-ui.sh 2>/dev/null || true
  fi

  echo "[git] pull --ff-only $remote $branch"
  if ! git pull --ff-only "$remote" "$branch"; then
    if [[ "${VOX_FORCE_PULL:-0}" == "1" ]]; then
      echo "[git] VOX_FORCE_PULL=1 — stash and retry"
      git stash push -u -m "voxbulk-deploy-force-pull $(date -Iseconds)" || true
      git pull --ff-only "$remote" "$branch" || {
        echo "[git] FAIL: pull failed after stash" >&2
        return 1
      }
    else
      echo "[git] FAIL: pull failed — run: VOX_FORCE_PULL=1 VOX_GIT_BRANCH=$branch bash scripts/vps-sync-all-ui.sh" >&2
      return 1
    fi
  fi

  local head_sha remote_sha
  head_sha=$(git rev-parse --short HEAD)
  remote_sha=$(git rev-parse --short "$remote_ref")

  if [[ "$head_sha" != "$remote_sha" ]]; then
    echo "[git] FAIL: local HEAD ($head_sha) != $remote_ref ($remote_sha)" >&2
    return 1
  fi

  echo "[git] OK at $head_sha — $(git log -1 --format='%s')"
  return 0
}

vox_verify_build_info_sha() {
  local root="${1:?repo root}"
  local wwwroot="${2:?wwwroot path}"
  local label="${3:-app}"

  local repo_sha
  repo_sha=$(git -C "$root" rev-parse --short HEAD 2>/dev/null || echo "")
  local info_file="$wwwroot/build-info.json"

  if [[ ! -f "$info_file" ]]; then
    echo "[verify] FAIL: $label missing $info_file" >&2
    return 1
  fi

  local deployed_sha
  deployed_sha=$(python3 - <<PY
import json
from pathlib import Path
data = json.loads(Path("$info_file").read_text())
print(data.get("git_sha") or "")
PY
)

  if [[ -z "$deployed_sha" ]]; then
    echo "[verify] FAIL: $label build-info.json has no git_sha" >&2
    return 1
  fi

  if [[ "$repo_sha" != "$deployed_sha" ]]; then
    echo "[verify] FAIL: $label SHA mismatch — repo=$repo_sha wwwroot=$deployed_sha" >&2
    echo "[verify]       nginx may point elsewhere, or build did not run prebuild sync:build-info" >&2
    return 1
  fi

  echo "[verify] OK $label build-info.json git_sha=$deployed_sha matches repo"
  return 0
}

vox_print_deploy_banner() {
  local status="${1:-COMPLETE}"
  local root="${2:?}"
  local sha branch built
  sha=$(git -C "$root" rev-parse --short HEAD 2>/dev/null || echo "?")
  branch=$(git -C "$root" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "?")
  built=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  if [[ "$status" == "COMPLETE" ]]; then
    cat <<EOF

══════════════════════════════════════════════════════════════
  DEPLOY COMPLETE
══════════════════════════════════════════════════════════════
  Branch:   $branch
  Commit:   $sha
  Built:    $built

  Verify in browser (Ctrl+Shift+R):
    https://dashboard.voxbulk.com/build-info.json
    https://admin.voxbulk.com/build-info.json

  build-info.json git_sha MUST equal commit $sha above.
  Log: ${VOX_DEPLOY_LOG:-/tmp/voxbulk-deploy.log}
══════════════════════════════════════════════════════════════
EOF
  else
    cat <<EOF

══════════════════════════════════════════════════════════════
  DEPLOY FAILED
══════════════════════════════════════════════════════════════
  Branch:   $branch
  Commit:   $sha
  Log: ${VOX_DEPLOY_LOG:-/tmp/voxbulk-deploy.log}
══════════════════════════════════════════════════════════════
EOF
  fi
}
