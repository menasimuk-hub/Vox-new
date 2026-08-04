#!/usr/bin/env bash
# Create aaPanel/nginx site for https://voxbox.voxbulk.com (static SPA).
# Run on VPS as deploy user with sudo: sudo bash scripts/vps-setup-voxbox-site.sh
set -euo pipefail

DOMAIN="voxbox.voxbulk.com"
WWWROOT="/www/wwwroot/${DOMAIN}"
NGINX_DIR="/www/server/panel/vhost/nginx"
CERT_DIR="/www/server/panel/vhost/cert/${DOMAIN}"
CONF="${NGINX_DIR}/${DOMAIN}.conf"
EXT_DIR="${NGINX_DIR}/extension/${DOMAIN}"
WELLKNOWN="${NGINX_DIR}/well-known/${DOMAIN}.conf"

echo "[voxbox] Creating wwwroot ${WWWROOT}"
mkdir -p "${WWWROOT}"
mkdir -p "${EXT_DIR}"
mkdir -p "$(dirname "${WELLKNOWN}")"
if [[ ! -f "${WWWROOT}/index.html" ]]; then
  cat > "${WWWROOT}/index.html" <<'HTML'
<!doctype html><html><head><meta charset="utf-8"><title>Voxbox</title></head>
<body><p>Voxbox — deploy pending. Run ./deploy-vps.sh</p></body></html>
HTML
fi

if [[ ! -f "${WELLKNOWN}" ]]; then
  cat > "${WELLKNOWN}" <<EOF
location ~ \.well-known {
    allow all;
}
EOF
fi

echo "[voxbox] Writing nginx vhost ${CONF}"
cat > "${CONF}" <<EOF
server
{
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};
    index index.html;
    root ${WWWROOT};
    include ${EXT_DIR}/*.conf;
    include ${WELLKNOWN};

    location / {
        return 301 https://\$host\$request_uri;
    }
    access_log  /www/wwwlogs/${DOMAIN}.log;
    error_log  /www/wwwlogs/${DOMAIN}.error.log;
}

server
{
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ${DOMAIN};
    index index.html;
    root ${WWWROOT};
    include ${EXT_DIR}/*.conf;
    include ${WELLKNOWN};

    #SSL-START
    ssl_certificate    ${CERT_DIR}/fullchain.pem;
    ssl_certificate_key    ${CERT_DIR}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    add_header Strict-Transport-Security "max-age=31536000";
    error_page 497  https://\$host\$request_uri;
    #SSL-END

    # Deny sensitive paths
    location ~ ^/(\.user.ini|\.htaccess|\.git|\.env|\.svn|\.project|LICENSE|README.md)
    {
        return 404;
    }

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    location ~ .*\.(gif|jpg|jpeg|png|bmp|swf|ico|webp|svg)$
    {
        expires 30d;
        access_log off;
    }

    location ~ .*\.(js|css|woff2?|ttf|eot)$
    {
        expires 12h;
        access_log off;
    }

    access_log  /www/wwwlogs/${DOMAIN}.log;
    error_log   /www/wwwlogs/${DOMAIN}.error.log;
}
EOF

# Issue / copy SSL if missing
if [[ ! -f "${CERT_DIR}/fullchain.pem" || ! -f "${CERT_DIR}/privkey.pem" ]]; then
  echo "[voxbox] SSL cert missing — attempting Let's Encrypt via aaPanel acme"
  mkdir -p "${CERT_DIR}"
  if [[ -f /www/server/panel/class/acme_v2.py ]]; then
    # Prefer panel ACME; fall back to certbot
    python3 - <<'PY' || true
import os, sys
sys.path.insert(0, "/www/server/panel/class")
try:
    import acme_v2
    # Best-effort; if this API differs, certbot path below runs.
    print("acme module loaded")
except Exception as e:
    print("acme import failed:", e)
PY
  fi
  if [[ ! -f "${CERT_DIR}/fullchain.pem" ]] && command -v certbot >/dev/null 2>&1; then
    certbot certonly --webroot -w "${WWWROOT}" -d "${DOMAIN}" --non-interactive --agree-tos \
      --register-unsafely-without-email || true
    LIVE="/etc/letsencrypt/live/${DOMAIN}"
    if [[ -f "${LIVE}/fullchain.pem" ]]; then
      cp -f "${LIVE}/fullchain.pem" "${CERT_DIR}/fullchain.pem"
      cp -f "${LIVE}/privkey.pem" "${CERT_DIR}/privkey.pem"
    fi
  fi
  # Last resort: reuse admin cert temporarily only if SAN includes voxbox (usually won't).
  if [[ ! -f "${CERT_DIR}/fullchain.pem" ]]; then
    echo "[voxbox] WARN: no SSL yet. Apply SSL in aaPanel → Website → ${DOMAIN} → SSL → Let's Encrypt."
    # Keep HTTP-only temporary conf so nginx -t still works
    cat > "${CONF}" <<EOF
server
{
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};
    index index.html;
    root ${WWWROOT};
    include ${EXT_DIR}/*.conf;
    include ${WELLKNOWN};

    location ~ ^/(\.user.ini|\.htaccess|\.git|\.env)
    {
        return 404;
    }

    location / {
        try_files \$uri \$uri/ /index.html;
    }
    access_log  /www/wwwlogs/${DOMAIN}.log;
    error_log  /www/wwwlogs/${DOMAIN}.error.log;
}
EOF
  fi
fi

# Register in aaPanel site list so it shows in Websites UI
if [[ -f /www/server/panel/data/db/site.db ]] || [[ -f /www/server/panel/data/default.db ]]; then
  echo "[voxbox] Registering site in aaPanel database (best-effort)"
  python3 - <<'PY' || true
import os, sqlite3, time
candidates = [
    "/www/server/panel/data/db/site.db",
    "/www/server/panel/data/default.db",
]
db = next((p for p in candidates if os.path.isfile(p)), None)
if not db:
    print("no panel db")
    raise SystemExit(0)
conn = sqlite3.connect(db)
cur = conn.cursor()
# Discover sites table
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("tables", tables[:20])
site_table = "sites" if "sites" in tables else ("site" if "site" in tables else None)
if not site_table:
    print("no sites table")
    raise SystemExit(0)
cols = [r[1] for r in cur.execute(f"PRAGMA table_info({site_table})").fetchall()]
print("cols", cols)
name = "voxbox.voxbulk.com"
exists = cur.execute(f"SELECT id FROM {site_table} WHERE name=?", (name,)).fetchone()
if exists:
    print("already registered id", exists[0])
else:
    now = int(time.time())
    # Minimal insert — column names vary by panel version
    payload = {}
    for c in cols:
        cl = c.lower()
        if cl == "name":
            payload[c] = name
        elif cl in ("path", "site_path"):
            payload[c] = "/www/wwwroot/voxbox.voxbulk.com"
        elif cl in ("status",):
            payload[c] = 1
        elif cl in ("ps", "remark"):
            payload[c] = "Voxbox unified inbox"
        elif cl in ("addtime", "created", "create_time"):
            payload[c] = now
        elif cl in ("type_id", "typeid"):
            payload[c] = 0
        elif cl == "project_type":
            payload[c] = "PHP"
        elif cl == "edate":
            payload[c] = "0000-00-00"
    keys = list(payload.keys())
    vals = [payload[k] for k in keys]
    sql = f"INSERT INTO {site_table} ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})"
    cur.execute(sql, vals)
    conn.commit()
    print("inserted", name)
conn.close()
PY
fi

nginx -t
nginx -s reload || systemctl reload nginx || true
echo "[voxbox] Site ready: http(s)://${DOMAIN} → ${WWWROOT}"
echo "[voxbox] If HTTPS fails, open aaPanel → Websites → Add site ${DOMAIN} or apply SSL manually."
