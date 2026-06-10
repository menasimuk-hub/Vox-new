# VOXBULK VPS deploy

## Push to GitHub ≠ live site

**Pushing from your PC updates GitHub only.** The VPS still serves old built files until you run a deploy script **on the server** (Baota → Terminal).

## Repo on VPS

```text
/www/voxbulk
```

GitHub repo: `https://github.com/menasimuk-hub/Vox-new.git`

---

## Billing + Stripe wallet fix (use this branch)

```text
feature/billing-system
```

**Do not deploy `main` for billing** — `main` still has the old free wallet top-up UI.

---

## Step 1 — SSH / Baota terminal on VPS

```bash
cd /www/voxbulk
```

---

## Step 2 — Full deploy (API + DB migrations + admin + dashboard)

```bash
cd /www/voxbulk
chmod +x deploy-vps.sh vox.sh scripts/vps-sync-all-ui.sh
VOX_GIT_BRANCH=feature/billing-system ./deploy-vps.sh
```

This will:

1. `git fetch` + checkout `feature/billing-system` + `git pull`
2. Run Alembic migrations (`voxbulk-api/`)
3. Build admin + dashboard frontends
4. Copy builds to `/www/wwwroot/admin.voxbulk.com` and `/www/wwwroot/dashboard.voxbulk.com`
5. Restart API + workers

If `git pull` fails:

```bash
cd /www/voxbulk
VOX_FORCE_PULL=1 VOX_GIT_BRANCH=feature/billing-system ./deploy-vps.sh
```

---

## Step 3 — Confirm deploy worked

Hard refresh browser: **Ctrl+Shift+R**

```text
https://dashboard.voxbulk.com/build-info.json
https://admin.voxbulk.com/build-info.json
```

`git_sha` must match:

```bash
cd /www/voxbulk
git log -1 --oneline
```

---

## Step 4 — Stripe in admin (required for wallet top-up)

1. Open **https://admin.voxbulk.com**
2. Go to **Integrations → Stripe**
3. Enable Stripe, paste **test** keys:
   - `pk_test_...` (publishable)
   - `sk_test_...` (secret)
4. Save and run **Test connection**

Wallet top-up will **not** work until Stripe shows as enabled here (not just in `.env`).

---

## Step 5 — Test wallet top-up

1. Open **https://dashboard.voxbulk.com/account/packages**
2. Click **Top up**
3. You must see **Pay with Card (Stripe)** and a **card form** (Stripe Elements)
4. Pay with test card: `4242 4242 4242 4242`, any future expiry, any CVC
5. Wallet balance increases **only after** card payment succeeds

If balance increases **without** a card form → dashboard is still old. Re-run Step 2.

---

## UI-only deploy (no API / no migrations)

```bash
cd /www/voxbulk
VOX_GIT_BRANCH=feature/billing-system bash scripts/vps-sync-all-ui.sh
```

---

## API only (no frontend rebuild)

```bash
cd /www/voxbulk
VOX_SKIP_BUILD=1 VOX_GIT_BRANCH=feature/billing-system ./deploy-vps.sh
```

---

## Skip flags

```bash
VOX_SKIP_GIT=1 ./deploy-vps.sh      # rebuild current tree only
VOX_SKIP_BUILD=1 ./deploy-vps.sh      # API + migrate only
VOX_SKIP_MIGRATE=1 ./deploy-vps.sh    # skip DB migrations
VOX_FORCE_PULL=1 ./deploy-vps.sh      # stash + retry pull
```

---

## wwwroot paths (Baota)

| App | Build output | Live wwwroot |
|-----|--------------|--------------|
| Admin | `admin.voxbulk.com/adim-web/dist/` | `/www/wwwroot/admin.voxbulk.com` |
| Dashboard | `dashboard.voxbulk.com/dashboard-web/dist/client/` | `/www/wwwroot/dashboard.voxbulk.com` |
| API | `voxbulk-api/` | systemd / `vox.sh` |

---

## Local dev directories (your PC)

| What | Path |
|------|------|
| Repo root | `C:\Users\zaghlol\Downloads\voxbulk.com` |
| API | `C:\Users\zaghlol\Downloads\voxbulk.com\voxbulk-api` |
| Dashboard | `C:\Users\zaghlol\Downloads\voxbulk.com\dashboard.voxbulk.com\dashboard-web` |
| Admin | `C:\Users\zaghlol\Downloads\voxbulk.com\admin.voxbulk.com\adim-web` |

Run API locally:

```powershell
cd C:\Users\zaghlol\Downloads\voxbulk.com\voxbulk-api
.\.venv\Scripts\activate
uvicorn main:app --reload --port 8000
```

Run dashboard locally:

```powershell
cd C:\Users\zaghlol\Downloads\voxbulk.com\dashboard.voxbulk.com\dashboard-web
npm run dev
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Wallet tops up without Stripe | VPS on wrong branch or old UI — run Step 2 with `feature/billing-system` |
| "Card payments are not configured" | Enable Stripe in admin integrations (Step 4) |
| `git_sha` stuck on old commit | `VOX_FORCE_PULL=1 VOX_GIT_BRANCH=feature/billing-system ./deploy-vps.sh` |
| `git pull` fails | Same as above with `VOX_FORCE_PULL=1` |
