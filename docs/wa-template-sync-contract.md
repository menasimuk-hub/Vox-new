# WhatsApp template sync contract (Survey + Customer Feedback)

**Owner:** Platform admin (VoxBulk).  
**Last updated:** 2026-07-09.

This document is the single reference for how local DB and Meta must stay aligned. Agents and developers must follow it before changing sync, push, or pull code.

---

## Principle

| Direction | Allowed | Forbidden |
|-----------|---------|-----------|
| **DB → Meta/Telnyx (push)** | Names, body, buttons, category from local draft | Guessing profile; silent platform Meta fallback when a Connection Profile is selected |
| **Meta → DB (pull)** | Status, rejection reason, remote template IDs | Names, body text, buttons, creating new survey/feedback rows from Meta catalog |

**Local DB is the source of truth for template content and naming.**

Meta/Telnyx are approval/runtime registries — we read **status** from providers, we do **not** clone remote catalogs into our product tables on routine sync.

---

## Dual catalog (Meta 99 + Telnyx 55)

Production uses two WhatsApp connection profiles:

| Role | Typical line | Purpose |
|------|--------------|---------|
| **Primary (default)** | Meta +447822002099 | All **outgoing sends** use the default profile |
| **Backup (hot standby)** | Telnyx +447822002055 | Catalog must stay **identical** to primary (same names, body, buttons from DB) |

Rules:

1. **Local edit + sync** → push same DB draft to **both** profiles (primary then backup mirror).
2. **Pull** → status only; never overwrite local names/bodies from Meta.
3. **No renames** in routine sync — Customer Feedback keeps `voxbulk_cf_*`; survey keeps `was_*`.
4. **Buttonless** system templates (thank-you, tell-us-more) → session text from server; **not** pushed to Meta.
5. **Failover** → set Telnyx 55 as default in Admin; sends switch to backup ledger template IDs.

Bulk dual push (VPS):

```bash
cd voxbulk-api && source .venv/bin/activate
python scripts/sync_wa_templates_both_profiles.py --scope all
python scripts/sync_wa_templates_both_profiles.py --scope customer_feedback --batch-size 10
```

Admin **Sync industry** (Customer Feedback): pushes all templates to Meta primary, mirrors to Telnyx backup, then pulls status from Meta.

---

## Connection Profiles (Meta 99, Telnyx 55)

- Every hub sync/push from Admin → WA Templates must send **`connection_profile_id`** for the selected profile.
- Push and send must use the **same** profile credentials (WABA, phone number ID, token).
- Profile **display name** is cosmetic; routing uses profile UUID + stored credentials.
- Per-profile status is stored in `wa_template_profile_status` (ledger); main template row reflects **primary** only.
- Outbound/inbound `whatsapp_logs` should record `connection_profile_id` when the business line is known.

Production Meta 99 reference (verify in Admin → Connection Profiles):

- Business ID: `959487190007928`
- Phone number ID: `1307579342430096`
- WABA: `1033532842963987`
- Phone: `+447822002099`

---

## Naming

| Product | Canonical prefix | Legacy (still on Meta until pushed) |
|---------|------------------|-------------------------------------|
| WA Survey | `was_{industry}_{topic}_{nnn}_{lang}` | `voxbulk_survey_{type}_{standard\|anonymous}` |
| Customer Feedback | `voxbulk_cf_*` | — |

Rename in DB first (scripts under `voxbulk-api/scripts/`), then **push** to both profiles. Never run catalog import between rename and push.

---

## Admin operations

### Refresh status (pull)

- API: `POST .../whatsapp-templates/sync-step/pull` with **`status_only: true`** (default).
- Updates approval state for rows already in DB matched by remote ID or name+language.
- Does **not** import Meta bodies or rename rows.

### Sync with Meta (hub job)

1. **Pull:** status only (`status_only: true`) — same as refresh.
2. **Push:** batches of local rows with `local_sync_status != in_sync`, from DB draft → primary profile.
3. **Mirror:** force-push same DB content to Telnyx backup (`mirror-backup` endpoints).

**Do not** use `status_only: false` / catalog import for survey or feedback in the hub.

### Push single template

- Sends **DB draft** to the selected Connection Profile via `push_template_to_both_profiles()` when dual sync is required.
- Response should include profile id and WABA for audit.

---

## Content restore (MD packs)

Survey question text and ABC buttons are authored in:

- `voxbulk-api/seed-data/wa-survey/employee-experience.md`
- `voxbulk-api/seed-data/wa-survey/all-industries-abc-templates.md`

Restore local DB from MD (no Meta):

```bash
cd voxbulk-api
python scripts/fix_employee_survey_local_db.py --apply
python scripts/rename_all_wa_survey_templates_local_db.py --apply
```

Reports: `voxbulk-api/seed-data/wa-survey/migration-reports/`

---

## Exceptions

- **`sync_from_meta` per system template row** — optional admin flag; when enabled, that single row may mirror Meta body on explicit refresh (not bulk hub pull).
- **Sales / interview / appointment** Telnyx catalog sync — separate admin endpoints; do not extend their Meta-import behaviour into survey/feedback hub paths.

---

## Regression tests

`tests/test_wa_template_sync_service.py` must include:

- Pull never overwrites local draft body.
- Pull never overwrites managed survey row name (`was_*`) with legacy Meta name.
- Backup profile send ID uses ledger only (no Meta UUID fallback when Telnyx is default).
- Dual push dry-run pushes to both profile slots.

---

## Checklist before VPS deploy

1. `pytest tests/test_wa_template_sync_service.py -q`
2. Hub sync uses `status_only: true` only.
3. No new code path sets `existing.name =` from Meta for survey/feedback rows on pull.
4. After deploy: `python scripts/sync_wa_templates_both_profiles.py --scope customer_feedback` or Sync industry per CF industry in Admin.
