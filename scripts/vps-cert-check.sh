#!/usr/bin/env bash
# Phase 0 — fail if site or mail TLS expires within 14 days.
# Run on the dedicated server:
#   cd /www/voxbulk && bash scripts/vps-cert-check.sh
# Cron (daily 06:00): 0 6 * * * /www/voxbulk/scripts/vps-cert-check.sh >> /tmp/voxbulk-cert-check.log 2>&1
set -euo pipefail

WARN_DAYS="${VOX_CERT_WARN_DAYS:-14}"
NOW_EPOCH="$(date +%s)"
CUTOFF=$((NOW_EPOCH + WARN_DAYS * 86400))
fail_count=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

check_pem() {
  local label="$1" path="$2" mode="${3:-fail}"
  if [[ ! -f "$path" ]]; then
    echo -e "${YELLOW}[skip]${NC} $label — missing $path"
    return 0
  fi
  local end
  end="$(openssl x509 -in "$path" -noout -enddate 2>/dev/null | sed 's/^notAfter=//')"
  if [[ -z "$end" ]]; then
    echo -e "${RED}[fail]${NC} $label — cannot parse $path"
    fail_count=$((fail_count + 1))
    return 0
  fi
  local end_epoch
  end_epoch="$(date -d "$end" +%s 2>/dev/null || true)"
  if [[ -z "$end_epoch" ]]; then
    echo -e "${YELLOW}[warn]${NC} $label — notAfter=$end (could not parse epoch)"
    return 0
  fi
  local days_left=$(( (end_epoch - NOW_EPOCH) / 86400 ))
  if [[ "$end_epoch" -lt "$NOW_EPOCH" ]]; then
    echo -e "${RED}[EXPIRED]${NC} $label — $end ($path)"
    fail_count=$((fail_count + 1))
  elif [[ "$end_epoch" -lt "$CUTOFF" ]]; then
    if [[ "$mode" == "warn" ]]; then
      echo -e "${YELLOW}[warn]${NC} $label — ${days_left}d left (notAfter $end) $path"
    else
      echo -e "${RED}[soon]${NC} $label — ${days_left}d left (notAfter $end) $path"
      fail_count=$((fail_count + 1))
    fi
  else
    echo -e "${GREEN}[ok]${NC} $label — ${days_left}d left (notAfter $end)"
  fi
}

check_live() {
  local label="$1" host="$2" port="${3:-443}"
  local end
  end="$(echo | openssl s_client -servername "$host" -connect "${host}:${port}" 2>/dev/null \
    | openssl x509 -noout -enddate 2>/dev/null | sed 's/^notAfter=//')"
  if [[ -z "$end" ]]; then
    echo -e "${YELLOW}[skip]${NC} live $label — no cert from ${host}:${port}"
    return 0
  fi
  local end_epoch
  end_epoch="$(date -d "$end" +%s 2>/dev/null || true)"
  local days_left=$(( (end_epoch - NOW_EPOCH) / 86400 ))
  if [[ -n "$end_epoch" && "$end_epoch" -lt "$CUTOFF" ]]; then
    echo -e "${RED}[soon]${NC} live $label — ${days_left}d left (notAfter $end)"
    fail_count=$((fail_count + 1))
  else
    echo -e "${GREEN}[ok]${NC} live $label — ${days_left}d left (notAfter $end)"
  fi
}

check_smtp() {
  local host="${VOX_SMTP_CHECK_HOST:-127.0.0.1}"
  local port="${VOX_SMTP_CHECK_PORT:-587}"
  local end
  end="$(echo | timeout 15 openssl s_client -starttls smtp -connect "${host}:${port}" -servername voxbulk.com 2>/dev/null \
    | openssl x509 -noout -enddate 2>/dev/null | sed 's/^notAfter=//')"
  if [[ -z "$end" ]]; then
    echo -e "${YELLOW}[skip]${NC} SMTP STARTTLS ${host}:${port} — no cert (or timeout)"
    return 0
  fi
  local end_epoch
  end_epoch="$(date -d "$end" +%s 2>/dev/null || true)"
  local days_left=$(( (end_epoch - NOW_EPOCH) / 86400 ))
  if [[ -n "$end_epoch" && "$end_epoch" -lt "$CUTOFF" ]]; then
    echo -e "${RED}[soon]${NC} SMTP :${port} — ${days_left}d left (notAfter $end)"
    fail_count=$((fail_count + 1))
  else
    echo -e "${GREEN}[ok]${NC} SMTP :${port} — ${days_left}d left (notAfter $end)"
  fi
}

echo "=== TLS expiry check (warn < ${WARN_DAYS} days) ==="
echo "time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

echo "--- files (aaPanel + mail_sys; needs read access) ---"
file_checks=0
for pair in \
  "nginx voxbulk.com|/www/server/panel/vhost/cert/voxbulk.com/fullchain.pem" \
  "nginx api.voxbulk.com|/www/server/panel/vhost/cert/api.voxbulk.com/fullchain.pem" \
  "nginx dashboard.voxbulk.com|/www/server/panel/vhost/cert/dashboard.voxbulk.com/fullchain.pem" \
  "nginx admin.voxbulk.com|/www/server/panel/vhost/cert/admin.voxbulk.com/fullchain.pem" \
  "mail_sys voxbulk.com|/www/server/panel/plugin/mail_sys/cert/voxbulk.com/fullchain.pem"; do
  label="${pair%%|*}"
  path="${pair#*|}"
  if [[ -r "$path" ]]; then
    check_pem "$label" "$path"
    file_checks=$((file_checks + 1))
  fi
done
# Discover ssl_certificate paths from aaPanel vhosts.
# Skip /www/server/panel/ssl/ (aaPanel default panel cert — not a public site).
# Other hosted domains: warn only. VOXBULK / mail / voxbox: fail if soon.
while IFS= read -r cert_path; do
  [[ -z "$cert_path" || ! -r "$cert_path" ]] && continue
  case "$cert_path" in
    /www/server/panel/ssl/*)
      echo -e "${YELLOW}[info]${NC} skip aaPanel panel cert $cert_path (renew in aaPanel → Panel SSL if the panel UI needs HTTPS)"
      continue
      ;;
  esac
  mode="warn"
  case "$cert_path" in
    *voxbulk*|*voxbox*|*mail_sys*) mode="fail" ;;
  esac
  check_pem "vhost $(basename "$(dirname "$cert_path")")" "$cert_path" "$mode"
  file_checks=$((file_checks + 1))
done < <(grep -hE '^\s*ssl_certificate\s+' /www/server/panel/vhost/nginx/*.conf 2>/dev/null \
  | awk '{print $2}' | tr -d ';' | sort -u || true)

if [[ -r /etc/letsencrypt/live/voxbulk.com/fullchain.pem ]]; then
  check_pem "letsencrypt voxbulk.com" /etc/letsencrypt/live/voxbulk.com/fullchain.pem
  file_checks=$((file_checks + 1))
fi
if [[ -r /etc/letsencrypt/live/api.voxbulk.com/fullchain.pem ]]; then
  check_pem "letsencrypt api" /etc/letsencrypt/live/api.voxbulk.com/fullchain.pem
  file_checks=$((file_checks + 1))
fi
if [[ "$file_checks" -eq 0 ]]; then
  echo -e "${YELLOW}[info]${NC} No cert files readable as this user (aaPanel dirs are often root-only)."
  echo "  Live HTTPS below is the source of truth. Optional: sudo bash scripts/vps-cert-check.sh"
fi

echo ""
echo "--- live HTTPS ---"
check_live "voxbulk.com" voxbulk.com
check_live "www.voxbulk.com" www.voxbulk.com
check_live "api.voxbulk.com" api.voxbulk.com
check_live "dashboard.voxbulk.com" dashboard.voxbulk.com
check_live "admin.voxbulk.com" admin.voxbulk.com

echo ""
echo "--- mail STARTTLS ---"
check_smtp

echo ""
if [[ "$fail_count" -gt 0 ]]; then
  echo -e "${RED}FAILED${NC} — $fail_count cert(s) expired or within ${WARN_DAYS} days."
  echo "Fix: sudo bash /www/voxbulk/scripts/fix-ssl-voxbulk.sh"
  echo "Then: sudo bash /www/voxbulk/scripts/vps-install-cert-renew-hook.sh"
  exit 1
fi
echo -e "${GREEN}OK${NC} — no certs within ${WARN_DAYS} days of expiry."
exit 0
