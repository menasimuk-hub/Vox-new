#!/usr/bin/env bash
# One-time (idempotent) VPS setup: systemd units for API + public preview (Restart=always).
#
# Usage on VPS:
#   cd /www/voxbulk
#   sudo bash scripts/vps-setup-api-systemd.sh
#   # or: ./vox.sh install-service
#
# Env:
#   VOX_UVICORN_WORKERS=2          gunicorn workers (use >=2 so reload stays online)
#   VOX_SYSTEMD_SKIP_START=1       write+enable units but do not start/restart yet
#   VOX_SKIP_PUBLIC_SYSTEMD=1      default — public is static wwwroot (not vite preview)
#   VOX_INSTALL_PUBLIC_PREVIEW=1   also enable voxbulk-public (rollback only)
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$ROOT/voxbulk-api"
PUBLIC_DIR="$ROOT/voxbulk.com/frontend"
API_RUN="$ROOT/scripts/run-api.sh"
PUBLIC_RUN="$ROOT/scripts/run-public-preview.sh"
UVICORN_BIN="$API_DIR/.venv/bin/uvicorn"
GUNICORN_BIN="$API_DIR/.venv/bin/gunicorn"
WORKERS="${VOX_UVICORN_WORKERS:-${VOX_GUNICORN_WORKERS:-2}}"
API_UNIT="/etc/systemd/system/voxbulk-api.service"
API_B_UNIT="/etc/systemd/system/voxbulk-api-b.service"
PUBLIC_UNIT="/etc/systemd/system/voxbulk-public.service"
# Prefer /var/log/voxbulk (LogsDirectory=) — append:/tmp/... often hits status=209/STDOUT
# when the log is root-owned or unreadable by the service User=.
LOG_DIR="/var/log/voxbulk"
API_LOG="$LOG_DIR/api.log"
API_B_LOG="$LOG_DIR/api-b.log"
PUBLIC_LOG="$LOG_DIR/public.log"
# Compat symlinks for older scripts that tail /tmp/voxbulk-*.log
API_LOG_COMPAT="/tmp/voxbulk-api.log"
PUBLIC_LOG_COMPAT="/tmp/voxbulk-public.log"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[api-systemd]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*" >&2; }
fail()  { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || fail "Run with sudo: sudo bash scripts/vps-setup-api-systemd.sh"
[[ -d "$API_DIR" ]] || fail "API dir not found: $API_DIR"
command -v systemctl >/dev/null 2>&1 || fail "systemctl not found — systemd required"

# Prefer the user who invoked sudo (deploy user), not root.
RUN_USER="${SUDO_USER:-}"
if [[ -z "$RUN_USER" || "$RUN_USER" == "root" ]]; then
  if [[ -d "$API_DIR" ]]; then
    RUN_USER="$(stat -c '%U' "$API_DIR" 2>/dev/null || true)"
  fi
fi
[[ -n "$RUN_USER" && "$RUN_USER" != "root" ]] || RUN_USER="$(id -un)"
RUN_GROUP="$(id -gn "$RUN_USER" 2>/dev/null || echo "$RUN_USER")"

if [[ ! -x "$UVICORN_BIN" || ! -x "$GUNICORN_BIN" ]]; then
  info "Creating venv + installing deps (uvicorn/gunicorn) …"
  if [[ ! -d "$API_DIR/.venv" ]]; then
    sudo -u "$RUN_USER" python3 -m venv "$API_DIR/.venv"
  fi
  sudo -u "$RUN_USER" bash -c "source '$API_DIR/.venv/bin/activate' && pip install -q -U pip && pip install -q -r '$API_DIR/requirements.txt'"
fi
[[ -x "$UVICORN_BIN" ]] || fail "uvicorn still missing: $UVICORN_BIN — run ./deploy-vps.sh first"
[[ -x "$GUNICORN_BIN" ]] || fail "gunicorn still missing: $GUNICORN_BIN — pip install -r requirements.txt"
[[ -f "$API_RUN" ]] || fail "Missing $API_RUN"

chmod +x "$API_RUN" "$PUBLIC_RUN" 2>/dev/null || true
mkdir -p "$LOG_DIR"
touch "$API_LOG" "$API_B_LOG" "$PUBLIC_LOG"
chown -R "$RUN_USER:$RUN_GROUP" "$LOG_DIR"
chmod 755 "$LOG_DIR"
chmod 644 "$API_LOG" "$API_B_LOG" "$PUBLIC_LOG"
ln -sfn "$API_LOG" "$API_LOG_COMPAT"
ln -sfn "$API_B_LOG" /tmp/voxbulk-api-b.log
ln -sfn "$PUBLIC_LOG" "$PUBLIC_LOG_COMPAT"
# Clear stale root-owned /tmp logs that caused 209/STDOUT on append:
if [[ -f "$API_LOG_COMPAT" && ! -L "$API_LOG_COMPAT" ]]; then
  warn "Replacing non-symlink $API_LOG_COMPAT (was blocking systemd stdout)"
  rm -f "$API_LOG_COMPAT"
  ln -sfn "$API_LOG" "$API_LOG_COMPAT"
fi
if [[ -f "$PUBLIC_LOG_COMPAT" && ! -L "$PUBLIC_LOG_COMPAT" ]]; then
  warn "Replacing non-symlink $PUBLIC_LOG_COMPAT"
  rm -f "$PUBLIC_LOG_COMPAT"
  ln -sfn "$PUBLIC_LOG" "$PUBLIC_LOG_COMPAT"
fi

# Stop leftover nohup only when systemd is not already serving (never kill both live APIs).
A_ACTIVE=0
B_ACTIVE=0
systemctl is-active --quiet voxbulk-api.service 2>/dev/null && A_ACTIVE=1
systemctl is-active --quiet voxbulk-api-b.service 2>/dev/null && B_ACTIVE=1
if [[ "$A_ACTIVE" -eq 0 && "$B_ACTIVE" -eq 0 ]]; then
  info "Stopping leftover nohup uvicorn/gunicorn (units not active) …"
  pkill -f "uvicorn.*main:app" 2>/dev/null || true
  pkill -f "python -m uvicorn.*main:app" 2>/dev/null || true
  pkill -f "gunicorn.*main:app" 2>/dev/null || true
  sleep 1
  if command -v fuser >/dev/null 2>&1; then
    fuser -k 8000/tcp 2>/dev/null || true
    fuser -k 8001/tcp 2>/dev/null || true
  fi
else
  info "Leaving running API units in place (A active=$A_ACTIVE B active=$B_ACTIVE)"
fi

_write_api_unit() {
  local unit="$1" port="$2" log="$3" ident="$4" desc="$5"
  cat >"$unit" <<EOF
[Unit]
Description=$desc
After=network.target mysql.service mariadb.service redis.service redis-server.service
Wants=network-online.target
# Must be in [Unit] (not [Service]) on this systemd — avoids "Unknown key name" warning
StartLimitIntervalSec=0

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_GROUP
WorkingDirectory=$API_DIR
LogsDirectory=voxbulk
Environment=PYTHONUNBUFFERED=1
Environment=VOX_UVICORN_WORKERS=$WORKERS
Environment=VOX_API_HOST=127.0.0.1
Environment=VOX_API_PORT=$port
ExecStart=$API_RUN
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=3
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=60
StandardOutput=append:$log
StandardError=append:$log
SyslogIdentifier=$ident

[Install]
WantedBy=multi-user.target
EOF
}

info "Writing $API_UNIT (user=$RUN_USER workers=$WORKERS port=8000 — graceful reload via HUP)"
_write_api_unit "$API_UNIT" 8000 "$API_LOG" "voxbulk-api" "VoxBulk API A (gunicorn :8000)"

info "Writing $API_B_UNIT (user=$RUN_USER workers=$WORKERS port=8001)"
_write_api_unit "$API_B_UNIT" 8001 "$API_B_LOG" "voxbulk-api-b" "VoxBulk API B (gunicorn :8001)"

if [[ "${VOX_INSTALL_PUBLIC_PREVIEW:-0}" == "1" ]]; then
  [[ -f "$PUBLIC_RUN" ]] || fail "Missing $PUBLIC_RUN"
  # Resolve npm for the deploy user (n/nvm/aaPanel paths vary).
  NPM_BIN="$(sudo -u "$RUN_USER" bash -lc 'command -v npm' 2>/dev/null || true)"
  [[ -n "$NPM_BIN" ]] || NPM_BIN="$(command -v npm || true)"
  [[ -n "$NPM_BIN" ]] || warn "npm not found in PATH — public unit may fail until npm is on PATH for $RUN_USER"

  info "Writing $PUBLIC_UNIT (user=$RUN_USER) — rollback / preview only"
  cat >"$PUBLIC_UNIT" <<EOF
[Unit]
Description=VoxBulk public site (vite preview :5173)
After=network.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_GROUP
WorkingDirectory=$PUBLIC_DIR
LogsDirectory=voxbulk
ExecStart=$PUBLIC_RUN
Restart=always
RestartSec=3
KillMode=mixed
TimeoutStopSec=20
StandardOutput=append:$PUBLIC_LOG
StandardError=append:$PUBLIC_LOG
SyslogIdentifier=voxbulk-public
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
EOF
else
  info "Skipping vite preview unit (public site is static wwwroot). Rollback: VOX_INSTALL_PUBLIC_PREVIEW=1"
fi

info "daemon-reload + enable …"
systemctl daemon-reload
systemctl enable voxbulk-api.service
systemctl enable voxbulk-api-b.service
if [[ "${VOX_SKIP_PUBLIC_SYSTEMD:-1}" != "1" && -f "$PUBLIC_UNIT" ]]; then
  systemctl enable voxbulk-public.service
fi

if [[ "${VOX_SYSTEMD_SKIP_START:-0}" == "1" ]]; then
  info "Units installed; start skipped (VOX_SYSTEMD_SKIP_START=1)"
else
  if [[ "$A_ACTIVE" -eq 1 ]]; then
    info "API A already active — not restarting :8000"
  else
    info "Starting voxbulk-api (:8000) …"
    systemctl start voxbulk-api.service || systemctl restart voxbulk-api.service
  fi
  if [[ "$B_ACTIVE" -eq 1 ]]; then
    info "API B already active — not restarting :8001"
  else
    info "Starting voxbulk-api-b (:8001) …"
    systemctl start voxbulk-api-b.service || systemctl restart voxbulk-api-b.service
  fi
  if [[ "${VOX_SKIP_PUBLIC_SYSTEMD:-1}" != "1" && -f "$PUBLIC_UNIT" ]]; then
    info "Starting voxbulk-public …"
    systemctl restart voxbulk-public.service || warn "voxbulk-public failed to start — build public frontend first"
  else
    if systemctl is-enabled --quiet voxbulk-public.service 2>/dev/null; then
      info "Public site is static wwwroot — disabling vite preview unit"
      systemctl disable --now voxbulk-public.service 2>/dev/null || true
    fi
  fi
  sleep 2
  systemctl --no-pager --full status voxbulk-api.service || true
  systemctl --no-pager --full status voxbulk-api-b.service || true
  if [[ -f "$PUBLIC_UNIT" && "${VOX_SKIP_PUBLIC_SYSTEMD:-1}" != "1" ]]; then
    systemctl --no-pager --full status voxbulk-public.service || true
  fi
fi

cat <<NOTES

══════════════════════════════════════════════════════════════
Systemd always-on setup complete
══════════════════════════════════════════════════════════════
  API A:        systemctl status voxbulk-api      (:8000)
  API B:        systemctl status voxbulk-api-b    (:8001)
  Logs:         tail -f $API_LOG $API_B_LOG
  Control:      cd $ROOT && ./vox.sh start|stop|reload|status
  Re-install:   sudo bash $ROOT/scripts/vps-setup-api-systemd.sh
  nginx:        sudo bash $ROOT/scripts/vps-install-dual-api-nginx.sh
  Public site:  static /www/wwwroot/voxbulk.com (not vite preview)
                sudo bash $ROOT/scripts/vps-install-public-static-nginx.sh

After reboot, both API ports start automatically.
Celery remains under Supervisor: sudo bash $ROOT/scripts/vps-setup-celery.sh
NOTES
