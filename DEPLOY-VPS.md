# VOXBULK VPS deploy

## Push to GitHub ≠ live site

**Pushing from your PC updates GitHub only.** Run the deploy **on the VPS** (Baota → Terminal).

**Repo on VPS:** `/www/voxbulk`  
**Branch:** `feature/billing-system`  
**Latest commit (after interview WhatsApp compliance fix):** `1cfe708`

**Latest commits:** billing fix `99de381`+ — look for `billing_marker: billing-cancellation-statusbadge-v3` in build-info.json

---

## `./vox.sh restart` does NOT update the website

Restart only reloads the API process. Dashboard/admin are **static files** in `/www/wwwroot/`. You must run `deploy-vps.sh` or `vps-sync-all-ui.sh` and confirm `build-info.json` **git_sha** and **built_at** change.

**Diagnose on VPS:**

```bash
cd /www/voxbulk
git fetch origin feature/billing-system
git log -1 --oneline
git rev-parse --short origin/feature/billing-system
cat /www/wwwroot/dashboard.voxbulk.com/build-info.json
tail -50 /tmp/voxbulk-deploy.log
```

If repo HEAD is behind `origin/feature/billing-system`, pull did not run. Use hard reset:

```bash
cd /www/voxbulk && VOX_HARD_RESET=1 VOX_GIT_BRANCH=feature/billing-system bash scripts/vps-sync-all-ui.sh
```

Success looks like:
- `git log -1` shows `99de381` or newer
- `build-info.json` has new `built_at` timestamp
- `billing_marker` = `billing-cancellation-statusbadge-v3`

---

Run in **Baota → Terminal**:

```bash
cd /www/voxbulk && chmod +x deploy-vps.sh vox.sh scripts/vps-sync-all-ui.sh && VOX_GIT_BRANCH=feature/billing-system ./deploy-vps.sh
```

This pulls GitHub, runs DB migrations (including `0113` cancellation/refund review), rebuilds admin + dashboard, copies to wwwroot, and restarts API + workers.

**If `git pull` fails:**

```bash
cd /www/voxbulk && VOX_FORCE_PULL=1 VOX_GIT_BRANCH=feature/billing-system ./deploy-vps.sh
```

**If VPS is stuck on an old commit (`build-info.json` SHA wrong):**

```bash
cd /www/voxbulk && VOX_HARD_RESET=1 VOX_GIT_BRANCH=feature/billing-system ./deploy-vps.sh
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

`git_sha` should start with `1cfe708`.

---

## What this deploy includes

- Org subscription **cancel at period end** (customer billing page)
- Admin **refund review** + wallet credit (Org Control Center)
- Alembic migration **`0113_subscription_cancellation_refund_review`**

**Do not deploy `main` for billing** — billing work lives on `feature/billing-system`.

---

## Quick tests after deploy

**Customer**

1. https://dashboard.voxbulk.com/account/billing  
2. **Request cancellation** → status shows scheduled + end date  
3. Plan change hidden while cancellation is scheduled  

**Admin**

1. https://admin.voxbulk.com → Org Control Center → pick org  
2. **Subscription cancellation** + **Refund reviews** panels visible  
3. Can reverse / immediate cancel / resolve refund review  

**API health**

```bash
curl -s http://127.0.0.1:8000/health | head -c 400
```

---

## Other deploy modes

**UI only** (no API / no migrations):

```bash
cd /www/voxbulk && VOX_GIT_BRANCH=feature/billing-system bash scripts/vps-sync-all-ui.sh
```

**API + migrations only** (no frontend rebuild):

```bash
cd /www/voxbulk && VOX_SKIP_BUILD=1 VOX_GIT_BRANCH=feature/billing-system ./deploy-vps.sh
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
```

---

## Stripe wallet top-up (still required)

1. Admin → **Integrations → Stripe** → enable + save test/live keys  
2. Dashboard → **Packages** → **Top up** → must show Stripe card form  
3. Test card: `4242 4242 4242 4242`

---

## wwwroot paths (Baota)

| App | Build output | Live wwwroot |
|-----|--------------|--------------|
| Admin | `admin.voxbulk.com/adim-web/dist/` | `/www/wwwroot/admin.voxbulk.com` |
| Dashboard | `dashboard.voxbulk.com/dashboard-web/dist/client/` | `/www/wwwroot/dashboard.voxbulk.com` |
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
| `git_sha` stuck | `VOX_HARD_RESET=1 VOX_GIT_BRANCH=feature/billing-system ./deploy-vps.sh` |
| New API route 404 | `./vox.sh restart` after deploy |
| Wallet tops up without Stripe | Wrong branch or old UI — full deploy on `feature/billing-system` |
| Cancellation UI missing | Full deploy (not UI-only); migration must run |
