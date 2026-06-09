# VOXBULK VPS deploy

## Push to GitHub ≠ live site

**Pushing from your PC updates GitHub only.** The VPS still serves old built files until you run a deploy script **on the server** (Baota → Terminal).

## Correct branch (survey + interview work)

Active feature branch:

```text
fix/wa-interview-platform-templates
```

Always pass it explicitly until merged to `main`:

```bash
cd /www/voxbulk
VOX_GIT_BRANCH=fix/wa-interview-platform-templates bash scripts/vps-sync-all-ui.sh
```

## Recommended: full UI sync (admin + dashboard)

```bash
cd /www/voxbulk
chmod +x scripts/vps-sync-all-ui.sh deploy-vps.sh vox.sh
VOX_GIT_BRANCH=fix/wa-interview-platform-templates bash scripts/vps-sync-all-ui.sh
```

This script:

1. `git fetch` + **checkout branch** + `git pull --ff-only`
2. Builds admin + dashboard (+ public if present)
3. Rsyncs to `/www/wwwroot/admin.voxbulk.com` and `/www/wwwroot/dashboard.voxbulk.com`
4. Restarts services
5. **Fails if `build-info.json` git_sha ≠ repo HEAD** (proves deploy worked)

On success you see:

```text
══════════════════════════════════════════════════════════════
  DEPLOY COMPLETE
══════════════════════════════════════════════════════════════
```

## Full deploy (API + migrations + all UIs)

```bash
cd /www/voxbulk
VOX_GIT_BRANCH=fix/wa-interview-platform-templates ./deploy-vps.sh
```

`deploy-vps.sh` now **checks out** `VOX_GIT_BRANCH` before pull (old bug: it pulled into whatever branch VPS was on, often `main`).

## Confirm deploy worked

Hard refresh: **Ctrl+Shift+R**

```text
https://dashboard.voxbulk.com/build-info.json
```

`git_sha` must match the commit printed at end of deploy, e.g. `17fdba6` (not an older SHA like `0e4e93d` or `6bd607d`).

Also check:

```text
https://admin.voxbulk.com/build-info.json
```

## Dashboard only (not recommended)

```bash
VOX_GIT_BRANCH=fix/wa-interview-platform-templates bash scripts/vps-sync-dashboard.sh
```

**Warning:** admin stays stale. Prefer `vps-sync-all-ui.sh`.

## UI only, no git pull (after manual git pull)

```bash
cd /www/voxbulk
git fetch origin fix/wa-interview-platform-templates
git checkout fix/wa-interview-platform-templates
git pull --ff-only origin fix/wa-interview-platform-templates
bash scripts/vps-update-ui.sh
```

## Troubleshooting stale build-info.json

| Symptom | Cause | Fix |
|---------|-------|-----|
| `git_sha` stuck on old commit | Wrong branch or pull failed silently | Run `vps-sync-all-ui.sh` with `VOX_GIT_BRANCH=fix/wa-interview-platform-templates` |
| Deploy says OK but SHA wrong | nginx serves different wwwroot | Confirm `VOX_DASH_DIST=/www/wwwroot/dashboard.voxbulk.com` |
| `git pull` fails | Untracked brand files block merge | `VOX_FORCE_PULL=1 VOX_GIT_BRANCH=fix/wa-interview-platform-templates bash scripts/vps-sync-all-ui.sh` |
| Built_at updates but SHA same | `VOX_SKIP_GIT=1` or no new commits on branch | `git log -1 --oneline` on VPS must match GitHub |

Check VPS repo state:

```bash
cd /www/voxbulk
git branch --show-current
git log -1 --oneline
git fetch origin fix/wa-interview-platform-templates
git rev-parse --short HEAD
git rev-parse --short origin/fix/wa-interview-platform-templates
# These two SHAs must match before build
```

## Git remote

**Canonical repo:** `https://github.com/menasimuk-hub/Vox-new.git`

Do **not** use `menasimuk-hub/Vox` (legacy duplicate).

## Baota / aaPanel wwwroot paths

| App | Build output | wwwroot |
|-----|--------------|---------|
| Admin | `admin.voxbulk.com/adim-web/dist/` | `/www/wwwroot/admin.voxbulk.com` |
| Dashboard | `dashboard.voxbulk.com/dashboard-web/dist/client/` | `/www/wwwroot/dashboard.voxbulk.com` |

## Seed WA survey industries (VPS)

Do **not** use bare `python3` — system SQLAlchemy is too old (`DeclarativeBase` import fails). Use the API venv:

```bash
cd /www/voxbulk/voxbulk-api
bash scripts/seed_wa_survey_industries.sh
```

If `.venv` is missing, run `./deploy-vps.sh` once first (creates venv + installs deps).

## Skip flags

```bash
VOX_SKIP_GIT=1 ./deploy-vps.sh      # rebuild current tree only — SHA won't change
VOX_SKIP_BUILD=1 ./deploy-vps.sh    # API only — UI stays stale
VOX_SKIP_MIGRATE=1 ./deploy-vps.sh
VOX_FORCE_PULL=1 ./deploy-vps.sh    # stash + retry pull
```
