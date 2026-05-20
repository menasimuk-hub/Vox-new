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
git remote add voxnew https://github.com/menasimuk-hub/Vox-new.git   # if needed

python3 -m venv voxbulk-api/.venv
cp voxbulk-api/.env.example voxbulk-api/.env   # edit DATABASE_URL, secrets

# Optional: nginx static roots
export VOX_ADMIN_DIST=/var/www/admin.voxbulk.com
export VOX_DASH_DIST=/var/www/dashboard.voxbulk.com
export VOX_PUBLIC_DIST=/var/www/voxbulk.com

./deploy-vps.sh
```

## Git remotes (important)

| Remote | Repo | Status |
|--------|------|--------|
| **voxnew** | `menasimuk-hub/Vox-new` | Matches this codebase (`main`) |
| **origin** | `menasimuk-hub/Vox` | **Unrelated history** — do not pull without reset |

On VPS, prefer:

```bash
export VOX_GIT_REMOTE=voxnew
export VOX_GIT_BRANCH=main
./deploy-vps.sh
```

## Migrations in this release

- `0046_messaging_templates` — WhatsApp/SMS/email template tables
- `0047_email_template_html_defaults` — system email HTML bodies
- `0048_kb_file_scope` — lead / sales / org KB libraries

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `alembic` not found | Script uses `python -m alembic` inside `.venv` |
| API 404 on `/admin/messaging/*` | `./vox.sh restart` after pull |
| Port 8000 in use | `./vox.sh stop` then redeploy |
| KB files wrong library | Re-upload on Lead or Sales page (scoped upload) |
| `git pull` unrelated histories | `git fetch voxnew && git reset --hard voxnew/main` (destroys local VPS edits) |
| Admin blank after deploy | Set `VOX_ADMIN_DIST` and point nginx `root` to `dist` |
| Email templates Not Found | Run migrate + restart API |

## Skip flags

```bash
VOX_SKIP_GIT=1 ./deploy-vps.sh      # deploy current files only
VOX_SKIP_BUILD=1 ./deploy-vps.sh    # API + migrate only
VOX_SKIP_MIGRATE=1 ./deploy-vps.sh  # no DB changes
```
