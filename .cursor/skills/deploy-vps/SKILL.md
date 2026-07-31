---
name: deploy-vps
description: Deploy VoxBulk to the production Linux VPS (git pull + deploy-vps.sh) and recover from common git-pull conflicts. Use when the user wants to deploy, release, ship, or update production, or troubleshoot a blocked VPS git pull.
---

# Deploy VoxBulk to the VPS

Production deploys run **on the Linux VPS (Baota/aaPanel)** — never from Windows. The repo root is the folder containing `deploy-vps.sh`, `vox.sh`, and `voxbulk-api/`.

## Standard deploy (run on the VPS as the deploy user)

```bash
cd /path/to/Vox          # e.g. /www/voxbulk
chmod +x deploy-vps.sh vox.sh
./deploy-vps.sh           # NOT: sudo sh ./deploy-vps.sh
```

Equivalent: `./vox.sh update`. The script pulls `origin main`, builds the frontends, rsyncs to wwwroot, and runs migrations. It calls `sudo` internally where needed.

## What it deploys (Baota defaults)
- Admin → `/www/wwwroot/admin.voxbulk.com`
- Dashboard → `/www/wwwroot/dashboard.voxbulk.com`
- API (FastAPI) → `127.0.0.1:8000` via uvicorn (`vox.sh` / systemd `voxbulk-api`); public host `https://api.voxbulk.com`

## Always-on (first time or after reboot issues)
```bash
cd /www/voxbulk
./vox.sh install-service   # systemd Restart=always for API + public
./deploy-vps.sh
systemctl status voxbulk-api
```
New long-running VPS processes must follow `.cursor/rules/vps-systemd-always-on.mdc` (not nohup-only).

## Git pull blocked by untracked brand/logo files
If pull fails with "untracked working tree files would be overwritten" for `*/public/brand/*.png`, remove the untracked copies (safe) then redeploy:

```bash
cd /path/to/Vox
rm -f admin.voxbulk.com/adim-web/public/brand/icon-black.png \
  admin.voxbulk.com/adim-web/public/brand/icon-white.png \
  admin.voxbulk.com/adim-web/public/brand/logo-black.png \
  admin.voxbulk.com/adim-web/public/brand/logo-white.png \
  dashboard.voxbulk.com/dashboard-web/public/brand/icon-black.png \
  dashboard.voxbulk.com/dashboard-web/public/brand/icon-white.png \
  dashboard.voxbulk.com/dashboard-web/public/brand/logo-black.png \
  dashboard.voxbulk.com/dashboard-web/public/brand/logo-white.png
git pull origin main
./deploy-vps.sh
```
Newer `deploy-vps.sh` clears these automatically before pulling.

## Git pull blocked by `routeTree.gen.ts`
Vite/TanStack **regenerates** `routeTree.gen.ts` during dashboard build on the VPS. That dirties a tracked file, so the **next** `git pull` fails with “local changes would be overwritten”.

**Fix now (on VPS):**
```bash
cd /www/voxbulk
git checkout -- dashboard.voxbulk.com/dashboard-web/src/routeTree.gen.ts
./deploy-vps.sh
```
Or discard everything local and match GitHub:
```bash
cd /www/voxbulk
VOX_HARD_RESET=1 ./deploy-vps.sh
```
Newer `scripts/lib/vps-git-sync.sh` discards dirty `routeTree.gen.ts` automatically before pull.

## Skip / force flags
```bash
VOX_SKIP_GIT=1 ./deploy-vps.sh
VOX_SKIP_BUILD=1 ./deploy-vps.sh
VOX_SKIP_MIGRATE=1 ./deploy-vps.sh
VOX_FORCE_PULL=1 ./deploy-vps.sh   # stash + retry pull — use with care
```

## Guardrails
- Push/pull only to `origin` → `https://github.com/menasimuk-hub/Vox-new.git`, branch `main`. Never the legacy `Vox` repo.
- Never commit or expose `voxbulk-api/.env`.
- If the public site shows "Blocked request… host not allowed", ensure `voxbulk.com/frontend/vite.config.ts` `preview.allowedHosts` includes the domains, rebuild, then `./vox.sh restart`.
- This skill describes commands to run on the server; do not attempt to run the production deploy from the local Windows machine.
