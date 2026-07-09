# VPS deploy + push WhatsApp templates to Meta (and Telnyx backup)

**Repo:** `https://github.com/menasimuk-hub/Vox-new.git` — branch `main`  
**Server path:** `/www/voxbulk`  
**Profiles:** Meta 99 (+447822002099) = default sends · Telnyx 55 (+447822002055) = backup catalog

Local **database** is source of truth for template names and body text.  
**Push** = DB → Meta/Telnyx. **Pull** (after push) = Meta approval **status only** — never import bodies from Meta.

---

## Part A — Deploy new code to the server

SSH to the VPS, then:

```bash
cd /www/voxbulk
```

### If `git pull` fails (local edits on server)

You may see:

```text
error: Your local changes ... would be overwritten by merge:
  voxbulk-api/app/services/survey_whatsapp_template_service.py
  voxbulk-api/app/services/wa_template_sync_service.py
```

**Fix:** discard server-only edits and deploy from GitHub:

```bash
cd /www/voxbulk
VOX_HARD_RESET=1 ./deploy-vps.sh
```

### If git is clean

```bash
cd /www/voxbulk
./deploy-vps.sh
```

### Verify deploy

```bash
git log -1 --oneline
```

Expected tip (or newer):

```text
072bb5a Dual-profile WA sync, drawer fix, and inbound logging hardening.
```

Deploy log (if terminal is quiet):

```bash
tail -f /tmp/voxbulk-deploy.log
```

Admin UI after deploy: hard refresh (Ctrl+Shift+R) on `https://admin.voxbulk.com`

---

## Part B — Push templates (what sync means)

| Action | Push what | To where | Pull after? |
|--------|-----------|----------|-------------|
| **Edit one template → Sync** | That template only (if changed) | Meta 99 + Telnyx 55 | Optional refresh status |
| **Sync industry** (Admin UI) | Changed templates in that industry | Meta then Telnyx mirror | Yes — status from Meta only |
| **Bulk script** (below) | **All** Customer Feedback rows | Meta then Telnyx | Run status refresh in Admin after |

**Order is always:** push content → mirror backup → pull status (never pull bodies before push).

**Day-to-day:** only **changed** templates are pushed (like git).  
**First-time / rebuild:** use bulk script once to push everything.

---

## Part C — Push ALL Customer Feedback to Meta + Telnyx (bulk script)

Run **on the VPS** after Part A deploy.

### 1) Dry run (count only)

```bash
cd /www/voxbulk/voxbulk-api
source .venv/bin/activate

python -u scripts/sync_wa_templates_both_profiles.py \
  --scope customer_feedback \
  --dry-run \
  2>&1 | tee /tmp/cf-dual-sync-dryrun.log
```

### 2) Live push (Meta primary, then Telnyx backup)

```bash
cd /www/voxbulk/voxbulk-api
source .venv/bin/activate

LOG=/tmp/cf-dual-sync-$(date -u +%Y%m%dT%H%M%SZ).log

python -u scripts/sync_wa_templates_both_profiles.py \
  --scope customer_feedback \
  --batch-size 10 \
  --json \
  2>&1 | tee "$LOG"

echo "Log file: $LOG"
```

Watch in another SSH session:

```bash
tail -f /tmp/cf-dual-sync-*.log
```

### 3) Full JSON report (errors, profile IDs, batch counts)

```bash
ls -lt /www/voxbulk/voxbulk-api/seed-data/wa-survey/migration-reports/dual-profile-sync-*.json | head -3
cat /www/voxbulk/voxbulk-api/seed-data/wa-survey/migration-reports/dual-profile-sync-*.json | tail -1
```

(or open the newest `dual-profile-sync-*.json` file)

### 4) Pull approval status from Meta (after bulk push)

Bulk script does **not** pull status. In Admin:

1. `https://admin.voxbulk.com` → **WA Templates** → **Customer Feedback**
2. Open each industry → **Sync industry** (last step refreshes status from Meta)

Or use hub **Refresh status** on the CF tab (status only).

---

## Part D — Push one industry from Admin (with on-screen progress)

1. Admin → **WA Templates** → **Customer Feedback**
2. Click an industry (e.g. Hotel)
3. Click **Sync industry**
4. Progress dialog:
   - Push to **Meta 99** (primary)
   - Mirror to **Telnyx 55** (backup)
   - Pull **status** from Meta

Repeat per industry if not using the bulk script.

---

## Part E — Later: change one template only

1. Admin → WA Templates → open template → edit text → **Save**
2. Click **Sync** on that row (or open edit sheet → sync)
3. Only that template is pushed to the active profile; dual-push applies when backup mirror step runs

No need to re-run the bulk script unless you want a full rebuild.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `git pull` blocked by local files | `VOX_HARD_RESET=1 ./deploy-vps.sh` |
| Server still old commit | `git log -1` must show `072bb5a` or newer |
| Telnyx backup missing in Admin | Integrations → Connection Profiles — ensure Telnyx 55 exists |
| Push errors in JSON report | Open `dual-profile-sync-*.json` → `errors` array |
| API not responding after deploy | `cd /www/voxbulk && ./vox.sh restart` |

---

## Quick copy-paste (full flow)

```bash
# 1) Deploy
cd /www/voxbulk
VOX_HARD_RESET=1 ./deploy-vps.sh
git log -1 --oneline

# 2) Push all Customer Feedback to Meta + Telnyx
cd /www/voxbulk/voxbulk-api
source .venv/bin/activate
LOG=/tmp/cf-dual-sync-$(date -u +%Y%m%dT%H%M%SZ).log
python -u scripts/sync_wa_templates_both_profiles.py --scope customer_feedback --batch-size 10 --json 2>&1 | tee "$LOG"

# 3) Then refresh status in Admin (CF tab → Sync industry per industry, or Refresh status)
```
