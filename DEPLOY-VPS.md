# VOXBULK VPS deploy

## One-command update (on the server)

```bash
cd /path/to/Vox          # repo root
chmod +x vox.sh deploy-vps.sh
./deploy-vps.sh
# or
./vox.sh update
```

## First-time VPS setup

```bash
git clone https://github.com/menasimuk-hub/Vox-new.git Vox
cd Vox
python3 -m venv voxbulk-api/.venv
cp voxbulk-api/.env.example voxbulk-api/.env   # edit DATABASE_URL, secrets

# Optional: nginx static roots
export VOX_ADMIN_DIST=/var/www/admin.voxbulk.com
export VOX_DASH_DIST=/var/www/dashboard.voxbulk.com
export VOX_PUBLIC_DIST=/var/www/voxbulk.com

# Baota / aaPanel (this VPS) — nginx serves from wwwroot, NOT from repo dist:
# export VOX_ADMIN_DIST=/www/wwwroot/admin.voxbulk.com
# export VOX_DASH_DIST=/www/wwwroot/dashboard.voxbulk.com
# export VOX_PUBLIC_DIST=/www/wwwroot/voxbulk.com

./deploy-vps.sh
```

## Git remote (important)

**Canonical repo:** `https://github.com/menasimuk-hub/Vox-new.git` (`origin` → `main`)

Do **not** use `menasimuk-hub/Vox` (legacy duplicate).

```bash
git pull origin main
./deploy-vps.sh
```

## Migrations in this release

- `0046_messaging_templates` — WhatsApp/SMS/email template tables
- `0047_email_template_html_defaults` — system email HTML bodies
- `0048_kb_file_scope` — lead / sales / org KB libraries

## Baota / aaPanel VPS (wwwroot)

After `npm run build`, **copy admin dist and dashboard `dist/client` to wwwroot**:

```bash
rsync -a --exclude='.user.ini' /www/voxbulk/admin.voxbulk.com/adim-web/dist/ /www/wwwroot/admin.voxbulk.com/
rsync -a --exclude='.user.ini' /www/voxbulk/dashboard.voxbulk.com/dashboard-web/dist/client/ /www/wwwroot/dashboard.voxbulk.com/
```

See also: `dashboard.voxbulk.com/dashboard-web/BUILD-VPS.md`

Verify dashboard: view source — must **not** contain `tabler-icons` (old theme).

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `alembic` not found | Script uses `python -m alembic` inside `.venv` |
| API 404 on `/admin/messaging/*` | `./vox.sh restart` after pull |
| Port 8000 in use | `./vox.sh stop` then redeploy |
| `./vox.sh status` says API not responding but uvicorn running | API still starting (wait 10–20s) or check `/tmp/voxbulk-api.log`; set `TRUSTED_HOSTS=api.voxbulk.com,localhost,127.0.0.1` in `voxbulk-api/.env` |
| `retover-celery: ERROR (no such process)` | Optional — only if you use Celery via supervisor; safe to ignore otherwise |
| KB files wrong library | Re-upload on Lead or Sales page (scoped upload) |
| `git pull` unrelated histories | `git fetch origin && git reset --hard origin/main` (destroys local VPS edits) |
| Admin blank after deploy | Set `VOX_ADMIN_DIST` and point nginx `root` to `dist` |
| Dashboard shows old orange theme | Wrong rsync: use `dist/client/` not `dist/`. Rebuild + rsync — see `dashboard-web/BUILD-VPS.md` |
| Dashboard 502 after nginx change | Run `cd dashboard-web && npm run build && ./vox.sh restart`; check `/tmp/voxbulk-dashboard.log` |
| Email templates Not Found | Run migrate + restart API |

## Skip flags

```bash
VOX_SKIP_GIT=1 ./deploy-vps.sh      # deploy current files only
VOX_SKIP_BUILD=1 ./deploy-vps.sh    # API + migrate only
VOX_SKIP_MIGRATE=1 ./deploy-vps.sh  # no DB changes
```
