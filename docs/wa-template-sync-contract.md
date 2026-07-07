# WhatsApp template sync contract (Survey + Customer Feedback)

**Owner:** Platform admin (VoxBulk).  
**Last updated:** 2026-07-07.

This document is the single reference for how local DB and Meta must stay aligned. Agents and developers must follow it before changing sync, push, or pull code.

---

## Principle

| Direction | Allowed | Forbidden |
|-----------|---------|-----------|
| **DB → Meta (push)** | Names, body, buttons, category from local draft | Guessing profile; silent platform Meta fallback when a Connection Profile is selected |
| **Meta → DB (pull)** | Status, rejection reason, remote template IDs | Names, body text, buttons, creating new survey/feedback rows from Meta catalog |

**Local DB is the source of truth for template content and naming.**

Meta is the approval/runtime registry — we read **status** from Meta, we do **not** clone Meta's catalog into our product tables on routine sync.

---

## Connection Profiles (Meta 99, Telnyx 55)

- Every hub sync/push from Admin → WA Templates must send **`connection_profile_id`** for the selected profile.
- Push and send must use the **same** profile credentials (WABA, phone number ID, token).
- Profile **display name** is cosmetic; routing uses profile UUID + stored credentials.

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

Rename in DB first (scripts under `voxbulk-api/scripts/`), then **push** to Meta. Never run catalog import between rename and push.

---

## Admin operations

### Refresh status (pull)

- API: `POST .../whatsapp-templates/sync-step/pull` with **`status_only: true`** (default).
- Updates approval state for rows already in DB matched by remote ID or name+language.
- Does **not** import Meta bodies or rename rows.

### Sync with Meta (hub job)

1. **Pull:** status only (`status_only: true`) — same as refresh.
2. **Push:** batches of local rows with `local_sync_status != in_sync`, from DB draft → Meta.

**Do not** use `status_only: false` / catalog import for survey or feedback in the hub.

### Push single template

- Sends **DB draft** to Meta under the selected Connection Profile.
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

---

## Checklist before VPS deploy

1. `pytest tests/test_wa_template_sync_service.py -q`
2. Hub sync uses `status_only: true` only.
3. No new code path sets `existing.name =` from Meta for survey/feedback rows on pull.
