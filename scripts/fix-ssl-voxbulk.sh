#!/usr/bin/env bash
# Issue / refresh Let's Encrypt certs for voxbulk.com + api.voxbulk.com (webroot)
# and install them where aaPanel nginx AND Postfix mail_sys already point.
# Unix LF only. Run: sudo bash scripts/fix-ssl-voxbulk.sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Run: sudo bash $0"
  exit 1
fi

install_live() {
  local name="$1"
  local dest="$2"
  local src="/etc/letsencrypt/live/${name}"
  mkdir -p "${dest}"
  if [ ! -f "${src}/fullchain.pem" ]; then
    echo "MISSING ${src}/fullchain.pem"
    ls -la "${src}" || ls -la /etc/letsencrypt/live || true
    return 1
  fi
  local key=""
  if [ -f "${src}/privkey.pem" ]; then
    key="${src}/privkey.pem"
  elif [ -f "${src}/key.pem" ]; then
    key="${src}/key.pem"
  else
    echo "MISSING private key in ${src}"
    ls -la "${src}" || true
    return 1
  fi
  cp -L "${src}/fullchain.pem" "${dest}/fullchain.pem"
  cp -L "${key}" "${dest}/privkey.pem"
  chmod 644 "${dest}/fullchain.pem"
  chmod 600 "${dest}/privkey.pem"
  echo "Installed ${name} -> ${dest}"
}

mkdir -p /www/wwwroot/voxbulk.com/.well-known/acme-challenge
mkdir -p /www/wwwroot/api.voxbulk.com/.well-known/acme-challenge

echo "=== live certs before ==="
ls -la /etc/letsencrypt/live || true

echo "=== issuing voxbulk.com + www ==="
certbot certonly --webroot \
  --webroot-path /www/wwwroot/voxbulk.com \
  -d voxbulk.com -d www.voxbulk.com \
  --cert-name voxbulk.com \
  --non-interactive --agree-tos --register-unsafely-without-email

echo "=== issuing api.voxbulk.com ==="
certbot certonly --webroot \
  --webroot-path /www/wwwroot/api.voxbulk.com \
  -d api.voxbulk.com \
  --cert-name api.voxbulk.com \
  --non-interactive --agree-tos --register-unsafely-without-email

echo "=== live certs after ==="
ls -la /etc/letsencrypt/live
ls -la /etc/letsencrypt/live/voxbulk.com || true
ls -la /etc/letsencrypt/live/api.voxbulk.com || true

echo "=== copying into aaPanel nginx + mail_sys ==="
install_live voxbulk.com /www/server/panel/vhost/cert/voxbulk.com
install_live api.voxbulk.com /www/server/panel/vhost/cert/api.voxbulk.com
install_live voxbulk.com /www/server/panel/plugin/mail_sys/cert/voxbulk.com || true

if [ -f /etc/postfix/vmail_ssl.map ]; then
  echo "=== postfix SNI map ==="
  postmap -F hash:/etc/postfix/vmail_ssl.map || postmap hash:/etc/postfix/vmail_ssl.map
  postfix reload || true
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -f "$ROOT/scripts/vps-install-cert-renew-hook.sh" ]; then
  bash "$ROOT/scripts/vps-install-cert-renew-hook.sh"
else
  echo "WARN: vps-install-cert-renew-hook.sh missing — hook not refreshed"
fi

echo "=== nginx reload ==="
nginx -t
nginx -s reload

echo "=== installed dates ==="
openssl x509 -in /www/server/panel/vhost/cert/voxbulk.com/fullchain.pem -noout -subject -dates
openssl x509 -in /www/server/panel/vhost/cert/api.voxbulk.com/fullchain.pem -noout -subject -dates
if [ -f /www/server/panel/plugin/mail_sys/cert/voxbulk.com/fullchain.pem ]; then
  openssl x509 -in /www/server/panel/plugin/mail_sys/cert/voxbulk.com/fullchain.pem -noout -subject -dates
fi
echo DONE
