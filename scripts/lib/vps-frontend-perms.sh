#!/usr/bin/env bash
# Fix frontend tree ownership before npm ci (root-owned node_modules after sudo deploy).

vox_frontend_dir_needs_chown() {
  local dir="$1"
  [[ -d "$dir" ]] || return 1
  local lock="$dir/package-lock.json"
  local uid
  uid=$(id -u)

  if [[ ! -w "$dir" ]]; then return 0; fi
  if [[ -f "$lock" ]] && [[ ! -w "$lock" ]]; then return 0; fi

  if [[ -d "$dir/dist" ]] && [[ ! -w "$dir/dist" ]]; then return 0; fi
  if [[ -d "$dir/dist" ]] && find "$dir/dist" -maxdepth 3 ! -user "$uid" -print -quit 2>/dev/null | grep -q .; then
    return 0
  fi

  if [[ -d "$dir/node_modules" ]]; then
    [[ -w "$dir/node_modules" ]] || return 0
    if [[ -d "$dir/node_modules/.bin" ]] && [[ ! -w "$dir/node_modules/.bin" ]]; then
      return 0
    fi
    if find "$dir/node_modules" -maxdepth 4 ! -user "$uid" -print -quit 2>/dev/null | grep -q .; then
      return 0
    fi
  fi
  return 1
}

vox_ensure_frontend_dir_writable() {
  local dir="$1"
  [[ -d "$dir" ]] || return 0
  vox_frontend_dir_needs_chown "$dir" || return 0

  local me gn
  me=$(id -un)
  gn=$(id -gn)
  echo "[perms] $dir has permission issues (often root-owned node_modules/dist from prior sudo deploy) — fixing ownership …" >&2
  sudo chown -R "$me:$gn" "$dir" || {
    echo "[perms] FAIL: Could not chown $dir — run: sudo chown -R $(whoami) $dir" >&2
    return 1
  }
}

vox_npm_ci_or_install() {
  local dir="$1"
  [[ -d "$dir" ]] || {
    echo "[perms] FAIL: missing directory $dir" >&2
    return 1
  }

  vox_ensure_frontend_dir_writable "$dir" || return 1
  cd "$dir"

  local run_npm
  run_npm() {
    if [[ -f package-lock.json ]]; then
      npm ci || return 1
    else
      npm install
    fi
  }

  if run_npm; then
    return 0
  fi

  if [[ -f package-lock.json ]]; then
    echo "[npm] npm ci failed — syncing lock with npm install …" >&2
    vox_ensure_frontend_dir_writable "$dir" || return 1
    rm -rf node_modules
    npm install || return 1
    return 0
  fi

  echo "[npm] npm failed — removing node_modules and retrying after chown …" >&2
  vox_ensure_frontend_dir_writable "$dir" || return 1
  rm -rf node_modules
  run_npm
}
