#!/usr/bin/env bash
# One-time (idempotent) VPS setup: systemd units for API + public preview (Restart=always).
#
# Usage on VPS:
#   cd /www/voxbulk
#   sudo bash scripts/vps-setup-api-systemd.sh
#   # or: ./vox.sh install-service
#
# Env:
#   VOX_UVICORN_WORKERS=1          baked into API unit ExecStart
#   VOX_SYSTEMD_SKIP_START=1       write+enable units but do not start/restart yet
#   VOX_SKIP_PUBLIC_SYSTEMD=1      install API unit only
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$ROOT/voxbulk-api"
PUBLIC_DIR="$ROOT/voxbulk.com/frontend"
PUBLIC_RUN="$ROOT/scripts/run-public-preview.sh"
UVICORN_BIN="$API_DIR/.venv/bin/uvicorn"
WORKERS="${VOX_UVICORN_WORKERS:-1}"
API_UNIT="/etc/systemd/system/voxbulk-api.service"
PUBLIC_UNIT="/etc/systemd/system/voxbulk-public.service"
# Prefer /var/log/voxbulk (LogsDirectory=) — append:/tmp/... often hits status=209/STDOUT
# when the log is root-owned or unreadable by the service User=.
LOG_DIR="/var/log/voxbulk"
API_LOG="$LOG_DIR/api.log"
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

if [[ ! -x "$UVICORN_BIN" ]]; then
  info "Creating venv + installing deps (uvicorn missing) …"
  if [[ ! -d "$API_DIR/.venv" ]]; then
    sudo -u "$RUN_USER" python3 -m venv "$API_DIR/.venv"
  fi
  sudo -u "$RUN_USER" bash -c "source '$API_DIR/.venv/bin/activate' && pip install -q -U pip && pip install -q -r '$API_DIR/requirements.txt'"
fi
[[ -x "$UVICORN_BIN" ]] || fail "uvicorn still missing: $UVICORN_BIN — run ./deploy-vps.sh first"

chmod +x "$PUBLIC_RUN" 2>/dev/null || true
mkdir -p "$LOG_DIR"
touch "$API_LOG" "$PUBLIC_LOG"
chown -R "$RUN_USER:$RUN_GROUP" "$LOG_DIR"
chmod 755 "$LOG_DIR"
chmod 644 "$API_LOG" "$PUBLIC_LOG"
ln -sfn "$API_LOG" "$API_LOG_COMPAT"
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

# Stop orphan nohup processes so only systemd owns the ports.
info "Stopping leftover nohup uvicorn / vite preview (if any) …"
pkill -f "uvicorn.*main:app" 2>/dev/null || true
pkill -f "python -m uvicorn.*main:app" 2>/dev/null || true
pkill -f "vite preview.*5173" 2>/dev/null || true
pkill -f "npm run preview.*5173" 2>/dev/null || true
sleep 1
if command -v fuser >/dev/null 2>&1; then
  fuser -k 8000/tcp 2>/dev/null || true
  fuser -k 5173/tcp 2>/dev/null || true
fi

info "Writing $API_UNIT (user=$RUN_USER workers=$WORKERS)"
cat >"$API_UNIT" <<EOF
[Unit]
Description=VoxBulk API (uvicorn)
After=network.target mysql.service mariadb.service redis.service redis-server.service
Wants=network-online.target
# Must be in [Unit] (not [Service]) on this systemd — avoids "Unknown key name" warning
StartLimitIntervalSec=0

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_GROUP
WorkingDirectory=$API_DIR
# systemd creates /var/log/voxbulk owned by User= — avoids 209/STDOUT on /tmp
LogsDirectory=voxbulk
ExecStart=$UVICORN_BIN main:app --host 127.0.0.1 --port 8000 --workers $WORKERS
Restart=always
RestartSec=3
KillMode=mixed
TimeoutStopSec=30
StandardOutput=append:$API_LOG
StandardError=append:$API_LOG
SyslogIdentifier=voxbulk-api
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

if [[ "${VOX_SKIP_PUBLIC_SYSTEMD:-0}" != "1" ]]; then
  [[ -f "$PUBLIC_RUN" ]] || fail "Missing $PUBLIC_RUN"
  # Resolve npm for the deploy user (n/nvm/aaPanel paths vary).
  NPM_BIN="$(sudo -u "$RUN_USER" bash -lc 'command -v npm' 2>/dev/null || true)"
  [[ -n "$NPM_BIN" ]] || NPM_BIN="$(command -v npm || true)"
  [[ -n "$NPM_BIN" ]] || warn "npm not found in PATH — public unit may fail until npm is on PATH for $RUN_USER"

  info "Writing $PUBLIC_UNIT (user=$RUN_USER)"
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
  warn "Skipping public systemd unit (VOX_SKIP_PUBLIC_SYSTEMD=1)"
fi

info "daemon-reload + enable …"
systemctl daemon-reload
systemctl enable voxbulk-api.service
if [[ "${VOX_SKIP_PUBLIC_SYSTEMD:-0}" != "1" && -f "$PUBLIC_UNIT" ]]; then
  systemctl enable voxbulk-public.service
fi

if [[ "${VOX_SYSTEMD_SKIP_START:-0}" == "1" ]]; then
  info "Units installed; start skipped (VOX_SYSTEMD_SKIP_START=1)"
else
  info "Starting voxbulk-api …"
  systemctl restart voxbulk-api.service
  if [[ "${VOX_SKIP_PUBLIC_SYSTEMD:-0}" != "1" && -f "$PUBLIC_UNIT" ]]; then
    info "Starting voxbulk-public …"
    systemctl restart voxbulk-public.service || warn "voxbulk-public failed to start — build public frontend first"
  fi
  sleep 2
  systemctl --no-pager --full status voxbulk-api.service || true
  if [[ -f "$PUBLIC_UNIT" ]]; then
    systemctl --no-pager --full status voxbulk-public.service || true
  fi
fi

cat <<NOTES

══════════════════════════════════════════════════════════════
Systemd always-on setup complete
══════════════════════════════════════════════════════════════
  API unit:     systemctl status voxbulk-api
  Public unit:  systemctl status voxbulk-public
  Logs:         tail -f $API_LOG
                journalctl -u voxbulk-api -f
  Control:      cd $ROOT && ./vox.sh start|stop|restart|status
  Re-install:   sudo bash $ROOT/scripts/vps-setup-api-systemd.sh
  If 209/STDOUT: re-run this script (fixes log path / ownership)

After reboot, API (+ public preview) start automatically.
Celery remains under Supervisor: sudo bash $ROOT/scripts/vps-setup-celery.sh
NOTES
