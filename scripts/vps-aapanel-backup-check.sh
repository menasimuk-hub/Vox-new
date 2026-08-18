#!/usr/bin/env bash
# Phase 0 — verify aaPanel scheduled backup (do NOT add a second mysqldump cron).
# Run on the dedicated server:
#   cd /www/voxbulk && bash scripts/vps-aapanel-backup-check.sh
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
ok() { echo -e "${GREEN}[ok]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
fail() { echo -e "${RED}[gap]${NC} $*"; }

echo "=== aaPanel backup check (no extra dump cron) ==="
echo "time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

BACKUP_ROOT="${VOX_BACKUP_ROOT:-/www/backup}"
PANEL_CRON="${VOX_PANEL_CRONTAB:-/www/server/panel/data/crontab.json}"
DAYS="${VOX_BACKUP_MAX_AGE_DAYS:-2}"
cutoff_epoch=$(($(date +%s) - DAYS * 86400))
fresh=0
remote_hint=0

if [[ -d "$BACKUP_ROOT" ]]; then
  ok "Backup directory exists: $BACKUP_ROOT"
  echo "--- newest files under $BACKUP_ROOT (depth 3) ---"
  # shellcheck disable=SC2012
  find "$BACKUP_ROOT" -type f \( -name '*.sql' -o -name '*.sql.gz' -o -name '*.tar.gz' -o -name '*.zip' -o -name '*.tgz' \) \
    -printf '%T@ %TY-%Tm-%Td %TH:%TM %s %p\n' 2>/dev/null \
    | sort -nr | head -20 | while read -r epoch rest; do
      echo "  $rest"
    done || ls -lt "$BACKUP_ROOT" 2>/dev/null | head -15
  newest="$(find "$BACKUP_ROOT" -type f \( -name '*.sql' -o -name '*.sql.gz' -o -name '*.tar.gz' -o -name '*.zip' \) -printf '%T@\n' 2>/dev/null | sort -nr | head -1 || true)"
  if [[ -n "${newest:-}" ]]; then
    newest_int="${newest%.*}"
    if [[ "$newest_int" -ge "$cutoff_epoch" ]]; then
      ok "A backup file is newer than ${DAYS} days"
      fresh=1
    else
      fail "Newest backup under $BACKUP_ROOT is older than ${DAYS} days — check aaPanel scheduled task"
    fi
  else
    fail "No .sql/.sql.gz/.tar.gz backup files found under $BACKUP_ROOT"
  fi
else
  fail "Missing $BACKUP_ROOT — aaPanel Backup plugin may use another path"
fi

echo ""
echo "--- crontab (system + typical panel users) ---"
for user in root www qusay; do
  if crontab -u "$user" -l 2>/dev/null | grep -qiE 'backup|mysqldump|btbackup'; then
    ok "User $user has a backup-related cron line"
    crontab -u "$user" -l 2>/dev/null | grep -iE 'backup|mysqldump|btbackup' || true
  fi
done
if crontab -l 2>/dev/null | grep -qiE 'backup|mysqldump|btbackup'; then
  ok "Current user crontab mentions backup"
  crontab -l 2>/dev/null | grep -iE 'backup|mysqldump|btbackup' || true
fi

echo ""
echo "--- aaPanel / remote destination hints ---"
if [[ -f "$PANEL_CRON" ]]; then
  if grep -qiE 'backup|ftp|s3|oss|cos|google|dropbox|webdav' "$PANEL_CRON" 2>/dev/null; then
    ok "crontab.json mentions backup or a remote store (inspect in aaPanel UI)"
  else
    warn "Could not see backup/remote keywords in $PANEL_CRON — confirm in aaPanel → Cron / Backup"
  fi
else
  warn "Panel crontab JSON not at $PANEL_CRON (aaPanel version may differ)"
fi

for plugin in \
  /www/server/panel/plugin/backup \
  /www/server/panel/plugin/cos \
  /www/server/panel/plugin/oss \
  /www/server/panel/plugin/aws_s3 \
  /www/server/panel/plugin/ftp \
  /www/server/panel/plugin/rsync; do
  if [[ -d "$plugin" ]]; then
    ok "Plugin dir present: $plugin"
    remote_hint=1
  fi
done
if [[ "$remote_hint" -eq 0 ]]; then
  fail "No obvious remote-backup plugin dir. If dumps only live on this disk, a disk failure loses MySQL + the backups."
  echo "  Fix in aaPanel: Backup → add FTP / S3 / rsync to another machine (do not add a second dump cron in this repo)."
fi

echo ""
echo "=== restore drill (run once, not every deploy) ==="
cat <<'DRILL'
1. In aaPanel → Backup, note the latest MySQL dump filename.
2. Create a TEMP database (never overwrite production):
     mysql -e "CREATE DATABASE voxbulk_restore_drill CHARACTER SET utf8mb4;"
3. Restore into the temp DB only:
     gunzip -c /www/backup/database/<file>.sql.gz | mysql voxbulk_restore_drill
4. Confirm tables + alembic:
     mysql voxbulk_restore_drill -e "SHOW TABLES;" | head
     mysql voxbulk_restore_drill -e "SELECT version_num FROM alembic_version;"
5. Drop the drill DB:
     mysql -e "DROP DATABASE voxbulk_restore_drill;"
6. Record date + dump filename in ops notes.

Do NOT add scripts/vps-mysql-backup.sh — aaPanel scheduled backup is the system of record.
DRILL

echo ""
if [[ "$fresh" -eq 1 && "$remote_hint" -eq 1 ]]; then
  ok "Backup looks scheduled and a remote plugin is installed — still confirm the last job copied off-box in aaPanel."
  exit 0
fi
if [[ "$fresh" -eq 1 ]]; then
  warn "Local dumps look fresh, but off-server copy was not proven. Check aaPanel Backup destination."
  exit 0
fi
exit 1
