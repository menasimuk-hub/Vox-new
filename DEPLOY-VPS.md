# VOXBULK VPS deploy

## Phase 0 — backups, TLS, uptime, production env

Run **on the dedicated server** after `git pull` (not from Windows). aaPanel scheduled backup stays the backup system — this repo does **not** add a second `mysqldump` cron.

```bash
cd /www/voxbulk
git pull origin main
chmod +x scripts/vps-*.sh scripts/celery-rolling-refresh.sh scripts/fix-ssl-voxbulk.sh

# 1) Confirm aaPanel dumps exist and hint if they are only on this disk
bash scripts/vps-aapanel-backup-check.sh

# 2) Production .env (does not print secret values)
bash scripts/vps-prod-env-check.sh

# 3) TLS files + live HTTPS + SMTP :587 (fails if < 14 days left)
bash scripts/vps-cert-check.sh

# 4) One-time: Certbot renew copies into aaPanel nginx AND Postfix mail_sys
sudo bash scripts/vps-install-cert-renew-hook.sh

# 5) Celery: wait up to 120s for in-flight jobs, then start (never pkill celery)
# Re-apply Supervisor stopwaitsecs=120:
sudo bash scripts/vps-setup-celery.sh
```

**aaPanel Backup:** in the panel, confirm the scheduled MySQL job copies **off this server** (FTP/S3/rsync), not only `/www/backup` on the same disk. Run the restore drill printed by `vps-aapanel-backup-check.sh` once.

**External uptime (no Cloudflare):** ping from a third party (UptimeRobot, Better Stack, or similar) — not from this machine:

| Check | URL / port |
|-------|------------|
| API | `https://api.voxbulk.com/health` |
| Public | `https://voxbulk.com` |
| Dashboard | `https://dashboard.voxbulk.com` |
| Admin | `https://admin.voxbulk.com` |
| Mail | SMTP STARTTLS `voxbulk.com:587` if the monitor supports it |

Alert email/SMS on failure. Do **not** put Cloudflare orange-cloud in front of the API or webhooks.

**Required `voxbulk-api/.env` on production:** `ENV=production`, `ALLOW_INSECURE_WEBHOOKS=0`, strong `JWT_SECRET_KEY` + `ENCRYPTION_KEY` (not `change-me`), `HEALTH_SECRET_TOKEN` set (`bash scripts/vps-set-health-token.sh` then one API restart), `PUBLIC_APP_ORIGIN=https://voxbulk.com`, `DASHBOARD_APP_ORIGIN=https://dashboard.voxbulk.com`.

---

## Smart Card public rate limit (aaPanel nginx — no Cloudflare)

One-time on the VPS after `git pull` (edge flood brake for `/public/smart-card/` on `api.voxbulk.com`):

```bash
cd /www/voxbulk
git pull origin main
sudo bash scripts/vps-install-smart-card-nginx-limit.sh
```

Adds `limit_req_zone sc_public` (http include) + `location ^~ /public/smart-card/` with `burst=60`. App-side reveal + IP/token limits still apply after deploy. Phone scans should stay fine; aggressive `curl` should eventually get **429**.

---

## Always-on API (systemd)

API + public preview can run under **systemd** (`Restart=always`) so they come back after a crash or VPS reboot — no manual `./vox.sh start` after reboot.

**One-time on the VPS** (after `git pull`):

```bash
cd /www/voxbulk
./vox.sh install-service
# same as: sudo bash scripts/vps-setup-api-systemd.sh
./deploy-vps.sh
systemctl status voxbulk-api
./vox.sh status
```

Afterwards, `./deploy-vps.sh` **reloads** the API via gunicorn (`systemctl reload`) so `:8000` stays up during deploy. Admin/dashboard are static (no downtime). Public vite preview may blip briefly on restart. Celery uses a **rolling Supervisor stop→start** (`scripts/celery-rolling-refresh.sh`, `stopwaitsecs=120`) so in-flight jobs can finish — never `pkill celery`. Hourly worker refresh uses the same rolling path.

**One-time upgrade** (if unit was installed before gunicorn reload support):

```bash
cd /www/voxbulk
git pull origin main
sudo bash scripts/vps-setup-api-systemd.sh
curl -s https://api.voxbulk.com/health
```

### If deploy dies with `status=209/STDOUT`

systemd could not open the log file (usually a root-owned `/tmp/voxbulk-api.log`). Fix:

```bash
cd /www/voxbulk
git pull origin main
sudo bash scripts/vps-fix-api-systemd-stdout.sh
# or: sudo bash scripts/vps-setup-api-systemd.sh
curl -s -H "Host: api.voxbulk.com" http://127.0.0.1:8000/health
```

---

## Push to GitHub ≠ live site

**Pushing from your PC updates GitHub only.** Run the deploy **on the VPS** (Baota → Terminal).

**Repo on VPS:** `/www/voxbulk`  
**Branch:** `fix/admin-finance-hardening`  
**Latest deploy:** Customer Feedback workflow (migration `0119_customer_feedback_workflow`)

---

## `./vox.sh restart` does NOT update the website

Restart only reloads the API process. Dashboard/admin are **static files** in `/www/wwwroot/`. You must run `deploy-vps.sh` or `vps-sync-all-ui.sh` and confirm `build-info.json` **git_sha** and **built_at** change.

**Diagnose on VPS:**

```bash
cd /www/voxbulk
git fetch origin fix/admin-finance-hardening
git log -1 --oneline
git rev-parse --short origin/fix/admin-finance-hardening
cat /www/wwwroot/dashboard.voxbulk.com/build-info.json
tail -50 /tmp/voxbulk-deploy.log
```

If repo HEAD is behind `origin/fix/admin-finance-hardening`, pull did not run. Use hard reset:

```bash
cd /www/voxbulk && VOX_HARD_RESET=1 VOX_GIT_BRANCH=fix/admin-finance-hardening bash scripts/vps-sync-all-ui.sh
```

Success looks like:
- `git log -1` shows the account-deletion commit (or newer)
- `build-info.json` has new `built_at` timestamp
- `curl -s -H "Host: api.voxbulk.com" http://127.0.0.1:8000/health` returns OK (plain `curl` without `Host` shows `Invalid host header` — that is normal)

---

## One command (full deploy)

Run in **Baota → Terminal**:

```bash
cd /www/voxbulk && chmod +x deploy-vps.sh vox.sh scripts/vps-sync-all-ui.sh && VOX_GIT_BRANCH=fix/admin-finance-hardening ./deploy-vps.sh
```

This pulls GitHub, runs DB migrations (including **`0119_customer_feedback_workflow`**), rebuilds admin + dashboard, copies to wwwroot, and restarts API + workers.

**If `git pull` fails:**

```bash
cd /www/voxbulk && VOX_FORCE_PULL=1 VOX_GIT_BRANCH=fix/admin-finance-hardening ./deploy-vps.sh
```

**If VPS is stuck on an old commit (`build-info.json` SHA wrong):**

```bash
cd /www/voxbulk && VOX_HARD_RESET=1 VOX_GIT_BRANCH=fix/admin-finance-hardening ./deploy-vps.sh
```

---

## Customer Feedback workflow — deploy checklist

Migration **must** run before or with the API deploy. `deploy-vps.sh` runs `alembic upgrade head` by default.

### 1. Confirm migration applied

```bash
cd /www/voxbulk/voxbulk-api
source .venv/bin/activate 2>/dev/null || true
python -m alembic current
python -m alembic history | head -5
```

Expected head revision includes **`0119_customer_feedback_workflow`**.

Manual migrate (if skipped):

```bash
cd /www/voxbulk/voxbulk-api && source .venv/bin/activate && python -m alembic upgrade head
```

### 2. Seed + import English templates

Industries/packages seed on first API call. Import 140 topic templates from Admin:

1. https://admin.voxbulk.com/customer-feedback/industries  
2. Click **Import English templates**

Or API (admin token):

```bash
curl -s -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{}' "https://api.voxbulk.com/admin/customer-feedback/templates/import-md"
```

### 3. Smoke test

```bash
curl -s -H "Host: api.voxbulk.com" http://127.0.0.1:8000/health
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.voxbulk.com/admin/customer-feedback/industries" | head -c 400
```

**Dashboard:** https://dashboard.voxbulk.com/feedback/new — create QR survey (multi-topic, opt-in toggle).

**Admin:** Industries, Packages pricing, Survey type edit (`/customer-feedback/survey-types/:id`).

### 4. WhatsApp inbound (production)

Ensure Telnyx webhook points at `https://api.voxbulk.com/...` for the feedback sender. Scan QR → send trigger → confirm 1 unit deducted and session starts.

---

## Account deletion workflow — deploy checklist

Migration **must** run before or with the API deploy. `deploy-vps.sh` runs `alembic upgrade head` by default.

### 1. Confirm migration applied

```bash
cd /www/voxbulk/voxbulk-api
source .venv/bin/activate 2>/dev/null || true
python -m alembic current
python -m alembic history | head -5
```

Expected head revision includes **`0118_account_deletion_requests`**.

Manual migrate (if you skipped it):

```bash
cd /www/voxbulk/voxbulk-api && source .venv/bin/activate && python -m alembic upgrade head
```

### 2. Seed email template

The `account_deletion_completed` template is in system defaults. After API boot, confirm in **Admin → Email** that the template exists, or trigger a one-off ensure:

```bash
cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
python -c "from app.core.database import get_sessionmaker; from app.services.email_template_service import EmailTemplateService; db=get_sessionmaker()(); EmailTemplateService.ensure_system_templates(db); db.commit(); print('ok')"
```

### 3. Restart API (if deploy used `VOX_SKIP_BUILD=1` only)

```bash
cd /www/voxbulk && ./vox.sh restart
```

### 4. Smoke test

```bash
cd /www/voxbulk && bash scripts/vps-workflow-smoke.sh
```

Optional authenticated checks:

```bash
VOXBULK_EMAIL=your@test.com VOXBULK_PASSWORD=... bash scripts/vps-workflow-smoke.sh --check-auth
```

### 5. Manual verification

**Customer (dashboard)**

1. https://dashboard.voxbulk.com/settings/profile  
2. Request deletion (type `DELETE`) → pending banner + “up to 2 working days”  
3. Other pages should 403 while pending; cancel restores access  
4. Settings → Audit → deletion events show **Deletion** badge  

**Admin**

1. https://admin.voxbulk.com → Dashboard → **Pending account deletions** card  
2. https://admin.voxbulk.com/compliance/account-deletions → queue, activity, **Complete deletion**  
3. Org Control Center → pending org shows red banner + **Complete account deletion**  
4. Organisation profile → pending badge + member deletion pills  

**API routes (admin token)**

```bash
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.voxbulk.com/admin/account-deletions?status_filter=pending"
```

---

## Confirm it worked

Hard refresh browser: **Ctrl+Shift+R**

Check SHA matches:

```bash
cd /www/voxbulk && git log -1 --oneline
```

Open:

- https://dashboard.voxbulk.com/build-info.json
- https://admin.voxbulk.com/build-info.json

`git_sha` should match `git log -1` on the VPS.

---

## What this deploy includes

- **Customer Feedback workflow** — QR → WhatsApp survey, multi-topic locations, per-inbound billing, admin industries/packages/survey-type editor  
- Migration **`0119_customer_feedback_workflow`** (location config, sessions, templates, marketing, promo wallet)  
- English template MD import (`seed-data/customer-feedback/english-templates.md`)  
- Prior branch work: account deletion, billing/finance hardening, welcome email  

---

## Other deploy modes

**UI only** (no API / no migrations):

```bash
cd /www/voxbulk && VOX_GIT_BRANCH=fix/admin-finance-hardening bash scripts/vps-sync-all-ui.sh
```

**API + migrations only** (no frontend rebuild):

```bash
cd /www/voxbulk && VOX_SKIP_BUILD=1 VOX_GIT_BRANCH=fix/admin-finance-hardening ./deploy-vps.sh
```

**Restart API only** (e.g. new routes but code already pulled):

```bash
cd /www/voxbulk && ./vox.sh restart
```

---

## Skip flags

```bash
VOX_SKIP_GIT=1 ./deploy-vps.sh      # rebuild current tree only
VOX_SKIP_BUILD=1 ./deploy-vps.sh    # API + migrate only
VOX_SKIP_MIGRATE=1 ./deploy-vps.sh  # skip DB migrations
VOX_FORCE_PULL=1 ./deploy-vps.sh    # stash + retry pull
VOX_HARD_RESET=1 ./deploy-vps.sh    # discard local edits (incl. routeTree.gen.ts) + match origin
```

**Why pull often fails after a successful deploy:** dashboard `npm run build` regenerates tracked `routeTree.gen.ts` on the VPS. The next pull then refuses to overwrite those local edits. Fix: `git checkout -- dashboard.voxbulk.com/dashboard-web/src/routeTree.gen.ts` then `./deploy-vps.sh`, or `VOX_HARD_RESET=1 ./deploy-vps.sh`. Deploy git sync now discards dirty `routeTree.gen.ts` automatically before pull.

---

## wwwroot paths (Baota)

| App | Build output | Live wwwroot |
|-----|--------------|--------------|
| Admin | `admin.voxbulk.com/adim-web/dist/` | `/www/wwwroot/admin.voxbulk.com` |
| Dashboard | `dashboard.voxbulk.com/dashboard-web/dist/client/` | `/www/wwwroot/dashboard.voxbulk.com` |
| Voxbox | `voxbox.voxbulk.com/voxbox-web/dist/` | `/www/wwwroot/voxbox.voxbulk.com` |

One-time Voxbox site (aaPanel/nginx): `sudo bash scripts/vps-setup-voxbox-site.sh` then apply SSL in aaPanel if needed. Set `VOXBOX_ADMIN_*` in `voxbulk-api/.env`.
| API | `voxbulk-api/` | systemd / `vox.sh` |

---

## Local dev (your PC)

| What | Path |
|------|------|
| Repo root | `C:\Users\zaghlol\Downloads\voxbulk.com` |
| API | `C:\Users\zaghlol\Downloads\voxbulk.com\voxbulk-api` |
| Dashboard | `C:\Users\zaghlol\Downloads\voxbulk.com\dashboard.voxbulk.com\dashboard-web` |
| Admin | `C:\Users\zaghlol\Downloads\voxbulk.com\admin.voxbulk.com\adim-web` |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Old UI after deploy | Re-run **One command** + hard refresh (`Ctrl+Shift+R`) |
| `git pull` / untracked files | `VOX_FORCE_PULL=1` or `VOX_HARD_RESET=1` (see above) |
| `routeTree.gen.ts` would be overwritten | `git checkout -- '**/routeTree.gen.ts'` then `./deploy-vps.sh`, or `VOX_HARD_RESET=1` |
| `git_sha` stuck | `VOX_HARD_RESET=1 VOX_GIT_BRANCH=fix/admin-finance-hardening ./deploy-vps.sh` |
| New API route 404 | `./vox.sh restart` after deploy |
| Deletion queue 404 | Migration `0118` not applied — run `alembic upgrade head` |
| No confirmation email | Check Admin → Email for `account_deletion_completed`; verify SMTP |
| User still has access after request | Hard refresh; pending users are blocked on all routes except cancel/status |
