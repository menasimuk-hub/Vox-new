#!/usr/bin/env bash
# Phase 0 — Certbot deploy hook: copy renewed LE certs into aaPanel nginx dirs AND mail_sys, then reload.
# Run once on the dedicated server:
#   cd /www/voxbulk && sudo bash scripts/vps-install-cert-renew-hook.sh
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run: sudo bash $0"
  exit 1
fi

HOOK="/etc/letsencrypt/renewal-hooks/deploy/copy-aapnel-voxbulk.sh"
mkdir -p /etc/letsencrypt/renewal-hooks/deploy

# Unix LF only — Windows CRLF broke this hook before (`set: pipefail`).
cat >"$HOOK" <<'HOOK'
#!/bin/bash
set -eu

copy_if() {
  local name="$1"
  local dest="$2"
  local src="/etc/letsencrypt/live/${name}"
  [ -f "${src}/fullchain.pem" ] || return 0
  mkdir -p "${dest}"
  local key="${src}/privkey.pem"
  [ -f "${key}" ] || key="${src}/key.pem"
  [ -f "${key}" ] || return 0
  cp -L "${src}/fullchain.pem" "${dest}/fullchain.pem"
  cp -L "${key}" "${dest}/privkey.pem"
  chmod 644 "${dest}/fullchain.pem"
  chmod 600 "${dest}/privkey.pem"
  echo "copied ${name} -> ${dest}"
}

copy_if voxbulk.com /www/server/panel/vhost/cert/voxbulk.com
copy_if api.voxbulk.com /www/server/panel/vhost/cert/api.voxbulk.com
copy_if dashboard.voxbulk.com /www/server/panel/vhost/cert/dashboard.voxbulk.com
copy_if admin.voxbulk.com /www/server/panel/vhost/cert/admin.voxbulk.com
copy_if voxbox.voxbulk.com /www/server/panel/vhost/cert/voxbox.voxbulk.com

# Postfix / aaPanel mail_sys uses a separate copy — nginx renew used to leave SMTP on the old cert.
copy_if voxbulk.com /www/server/panel/plugin/mail_sys/cert/voxbulk.com
if [ -f /www/server/panel/plugin/mail_sys/cert/voxbulk.com/privkey.pem ]; then
  cp -L /www/server/panel/plugin/mail_sys/cert/voxbulk.com/privkey.pem \
    /www/server/panel/plugin/mail_sys/cert/voxbulk.com/privkey.pem
fi

if [ -f /etc/postfix/vmail_ssl.map ]; then
  postmap -F hash:/etc/postfix/vmail_ssl.map >/dev/null 2>&1 || postmap hash:/etc/postfix/vmail_ssl.map >/dev/null 2>&1 || true
  postfix reload >/dev/null 2>&1 || true
fi

nginx -s reload >/dev/null 2>&1 || true
HOOK
chmod 755 "$HOOK"
# Strip CR if this file was ever copied from Windows.
sed -i 's/\r$//' "$HOOK" 2>/dev/null || true

echo "Installed $HOOK"

CRON_LINE="0 6 * * * /www/voxbulk/scripts/vps-cert-check.sh >> /tmp/voxbulk-cert-check.log 2>&1"
if command -v crontab >/dev/null 2>&1; then
  existing="$(crontab -l 2>/dev/null || true)"
  if echo "$existing" | grep -Fq "vps-cert-check.sh"; then
    echo "Cert-check cron already present"
  else
    printf '%s\n%s\n' "$existing" "$CRON_LINE" | crontab - || echo "Could not install crontab — add: $CRON_LINE"
    echo "Installed daily cert-check cron (06:00)"
  fi
fi

echo "Test: certbot renew --dry-run"
echo "Check: bash /www/voxbulk/scripts/vps-cert-check.sh"
