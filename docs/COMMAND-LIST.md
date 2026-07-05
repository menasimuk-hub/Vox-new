# VoxBulk command list

**Generated:** 2026-07-05 · **Total scripts:** 158

**Local repo:** `c:\Users\zaghlol\Downloads\voxbulk.com`
**VPS repo:** `/www/voxbulk`

> **Keep this list updated:** when you add or rename an ops script, run:
> ```bash
> python scripts/generate-command-list.py
> powershell scripts/regenerate-command-list-pdf.ps1   # Windows PDF
> ```

**Colored printable version:** `docs/COMMAND-LIST.html` → Print → Save as PDF

---

## DELETE USER COMPLETELY (IRREVERSIBLE)

### A) Salesman + org + all data (by email) — easiest

| | |
|---|---|
| **Shell wrapper** | `delete-salesman.sh` |
| **Python** | `voxbulk-api/scripts/delete_salesman.py` |

**VPS:**
```bash
cd /www/voxbulk
./delete-salesman.sh user@example.com          # dry run
./delete-salesman.sh user@example.com --yes    # DELETE EVERYTHING
```

**Windows:**
```powershell
cd c:\Users\zaghlol\Downloads\voxbulk.com\voxbulk-api
.\.venv\Scripts\Activate.ps1
python -m scripts.delete_salesman --email user@example.com
python -m scripts.delete_salesman --email user@example.com --yes
```

### B) Purge billing + hard-delete by user UUID

**Script:** `voxbulk-api/scripts/purge_user_billing_and_accounts.py`

```bash
cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
python scripts/purge_user_billing_and_accounts.py --dry-run --user-id UUID --delete-users --delete-solo-orgs
python scripts/purge_user_billing_and_accounts.py --apply --confirm PURGE_TEST_USERS --user-id UUID --delete-users --delete-solo-orgs
```


---

## SEED / DEMO DATA (start here)

All seed scripts run from **`voxbulk-api/`** with the project venv active unless noted.

### Quick start — full salesman demo (VPS)

```bash
cd /www/voxbulk
./seed-sales-demo.sh salesman1@voxbulk.com          # seed
./seed-sales-demo.sh salesman1@voxbulk.com --reset  # wipe + re-seed
```

### Quick start — rich demo for any dashboard user

```bash
cd /www/voxbulk/voxbulk-api
source .venv/bin/activate
python scripts/seed_demo_user_account.py --email user@example.com --clear --auto-top-up
```

**Windows (local):**

```powershell
cd c:\Users\zaghlol\Downloads\voxbulk.com\voxbulk-api
.\.venv\Scripts\Activate.ps1
python scripts/seed_demo_user_account.py --email user@example.com --clear --auto-top-up
```

### Enable all dashboard modules

```bash
python scripts/seed_demo_all_dashboard_services.py --email user@example.com
```

See the **full seed script table** below for every `seed_*` script.


---

## CUSTOMER FEEDBACK → META SYNC (VPS)

Push ~400 language rows per industry (~2,800 total across 7 industries) to Meta/Telnyx in **small batches** to avoid rate limits.

All commands run from **`voxbulk-api/`** with venv active.

### 1) Import templates from Markdown (optional — if not done in Admin)

```bash
cd /www/voxbulk/voxbulk-api && source .venv/bin/activate

# Dry-run first
python scripts/seed_feedback_industry_from_md.py \
  --industry fitness \
  --md seed-data/customer-feedback/fitness-gyms-20lang.md \
  --dry-run

# Import only (no Meta push)
python scripts/seed_feedback_industry_from_md.py \
  --industry fitness \
  --md seed-data/customer-feedback/fitness-gyms-20lang.md

# Import + push one industry (batched, 15s delay)
python scripts/seed_feedback_industry_from_md.py \
  --industry fitness \
  --md seed-data/customer-feedback/fitness-gyms-20lang.md \
  --push --push-batch-size 5 --push-delay-sec 15
```

### 2) Push all industries overnight (~3 hours) — recommended

```bash
cd /www/voxbulk/voxbulk-api && source .venv/bin/activate

# Dry-run (validate payloads, no Meta POST)
python -u scripts/push_all_feedback_to_meta_overnight.py --dry-run --industry-slug fitness

# Full run in background (use -u so log updates immediately)
nohup python -u scripts/push_all_feedback_to_meta_overnight.py \
  --batch-size 5 --delay-sec 15 --industry-delay-sec 45 \
  --no-resume \
  > /tmp/cf-meta-push.log 2>&1 &

echo $!   # note PID
```

### 3) Monitor while running

```bash
# Live log (should show new batch lines every ~20–60 sec)
tail -f /tmp/cf-meta-push.log

# Process still alive?
ps -p PID -o pid,etime,cmd

# Progress state file (offset increases each batch)
cat seed-data/customer-feedback/push-reports/push_all_feedback_state.json

# Reports folder (from inside voxbulk-api/)
ls -lt seed-data/customer-feedback/push-reports/
```

**Working:** log shows `=== Customer Feedback -> Meta overnight push ===`, then `batch 1 offset=0`, then `Pushed batch 1–5 of 400…`.

**Resume after interrupt:**

```bash
python -u scripts/push_all_feedback_to_meta_overnight.py --resume
```

### 4) Push one industry only (foreground)

```bash
python -u scripts/push_all_feedback_to_meta_overnight.py \
  --industry-slug restaurant --batch-size 5 --delay-sec 15
```

### 5) Push one industry — fast (no batch delays, use with care)

```bash
python scripts/push_feedback_industry_to_telnyx.py --industry-slug fitness
python scripts/push_feedback_industry_to_telnyx.py --industry-slug fitness --dry-run
```

### 6) When finished

```bash
tail -30 /tmp/cf-meta-push.log
# Expect: DONE | Industries completed: 7/7 | Failed: 0
cat seed-data/customer-feedback/push-reports/push-all-feedback-*.json
```

Check **Admin → Customer Feedback → industry → Sync status**, or **WhatsApp Manager** for names prefixed `voxbulk_cf_`.

### 7) System templates — local vs Meta sync (Survey + Feedback)

In **Admin → WA Templates → Survey or Feedback tab → System templates**:

| Mode | Behaviour |
|------|-----------|
| **Keep local** (default) | Admin draft/body is source of truth; **Sync** pushes local → Meta; pull updates status only |
| **Sync from Meta** | **Pull all from Meta** imports approved body/buttons into local; sends route from Meta mirror |

API (optional):

```bash
# Survey
curl -X PATCH .../admin/wa-survey/system-templates/routing -d '{"template_source":"meta_sync"}'
curl -X POST .../admin/wa-survey/system-templates/pull-from-meta

# Feedback
curl -X PATCH .../admin/customer-feedback/system-templates/routing -d '{"template_source":"local"}'
curl -X POST .../admin/customer-feedback/system-templates/pull-from-meta
```


---

## TEST NEW BILLING (Stripe / Airwallex / GoCardless)

```bash
cd /www/voxbulk && git pull origin main && ./deploy-vps.sh
bash scripts/verify-billing-deploy.sh
```

```powershell
cd voxbulk-api
pytest tests/test_card_subscription_checkout.py tests/test_stripe_subscription_renewal.py \
  tests/test_airwallex_subscription_renewal.py tests/test_card_renewal_lifecycle.py tests/test_card_plan_change.py -q
```

---

## ALL SCRIPTS (complete inventory)

### Root shell wrappers (4)

| Path | Description | Example command |
|------|-------------|-----------------|
| `delete-salesman.sh` | Delete salesman + org + ALL data (by email) | `./delete-salesman.sh EMAIL [--yes]` |
| `deploy-vps.sh` | Full deploy (pull, migrate, build, restart) | `./deploy-vps.sh` |
| `seed-sales-demo.sh` | Seed full salesman demo workspace (interviews, surveys, feedback QR) | `./seed-sales-demo.sh EMAIL [--reset]` |
| `vox.sh` | VPS service control | `./vox.sh start|stop|restart|status|update` |

### Delete user (2)

| Path | Description | Example command |
|------|-------------|-----------------|
| `voxbulk-api/scripts/delete_salesman.py` | Delete salesman + org (Python; see delete-salesman.sh) | `python -m scripts.delete_salesman --email EMAIL [--yes]` |
| `voxbulk-api/scripts/purge_user_billing_and_accounts.py` | Purge billing + hard-delete by user UUID | `python scripts/purge_user_billing_and_accounts.py --apply --confirm PURGE_TEST_USERS ...` |

### Seed / demo data (34)

| Path | Description | Example command |
|------|-------------|-----------------|
| `voxbulk-api/scripts/seed_appointment_gb_agents.py` | GB appointment voice agents | `python scripts/seed_appointment_gb_agents.py` |
| `voxbulk-api/scripts/seed_appointment_wa_survey_test_data.py` | Appointment + WA survey E2E test data | `python scripts/seed_appointment_wa_survey_test_data.py --help` |
| `voxbulk-api/scripts/seed_demo_all_dashboard_services.py` | Enable all dashboard menu modules for an org | `python scripts/seed_demo_all_dashboard_services.py --email EMAIL` |
| `voxbulk-api/scripts/seed_demo_appointments.py` | Demo CRM appointments | `python scripts/seed_demo_appointments.py --help` |
| `voxbulk-api/scripts/seed_demo_booking_link.py` | Demo public booking link | `python scripts/seed_demo_booking_link.py --help` |
| `voxbulk-api/scripts/seed_demo_survey_hubspot.py` | HubSpot sync demo surveys | `python scripts/seed_demo_survey_hubspot.py --help` |
| `voxbulk-api/scripts/seed_demo_survey_hubspot.sh` | seed demo survey hubspot | `bash voxbulk-api/scripts/seed_demo_survey_hubspot.sh` |
| `voxbulk-api/scripts/seed_demo_survey_mixed.py` | Mixed WA + AI phone survey demo data | `python scripts/seed_demo_survey_mixed.py --help` |
| `voxbulk-api/scripts/seed_demo_survey_mixed.sh` | seed demo survey mixed | `bash voxbulk-api/scripts/seed_demo_survey_mixed.sh` |
| `voxbulk-api/scripts/seed_demo_user_account.py` | Rich demo for any dashboard user (wallet debits, 3 campaigns) | `python scripts/seed_demo_user_account.py --email EMAIL --clear --auto-top-up` |
| `voxbulk-api/scripts/seed_dummy_interview.py` | Dummy interview UI test data | `python scripts/seed_dummy_interview.py --help` |
| `voxbulk-api/scripts/seed_dummy_survey.py` | Dummy completed AI-call survey | `python scripts/seed_dummy_survey.py --help` |
| `voxbulk-api/scripts/seed_dummy_survey.sh` | seed dummy survey | `bash voxbulk-api/scripts/seed_dummy_survey.sh` |
| `voxbulk-api/scripts/seed_feedback_acton.sh` | seed feedback acton | `bash voxbulk-api/scripts/seed_feedback_acton.sh` |
| `voxbulk-api/scripts/seed_feedback_ealing.sh` | seed feedback ealing | `bash voxbulk-api/scripts/seed_feedback_ealing.sh` |
| `voxbulk-api/scripts/seed_feedback_industry_from_md.py` | Import Customer Feedback industry templates from Markdown (+ optional Meta push) | `python scripts/seed_feedback_industry_from_md.py --industry fitness --md seed-data/customer-feedback/fitness-gyms-20lang.md --dry-run` |
| `voxbulk-api/scripts/seed_feedback_responses_mixed.py` | Feedback QR results (happy/unhappy mix) | `python scripts/seed_feedback_responses_mixed.py --help` |
| `voxbulk-api/scripts/seed_feedback_responses_mixed.sh` | seed feedback responses mixed | `bash voxbulk-api/scripts/seed_feedback_responses_mixed.sh` |
| `voxbulk-api/scripts/seed_hubspot_appointment_test_data.py` | HubSpot appointment test data | `python scripts/seed_hubspot_appointment_test_data.py --help` |
| `voxbulk-api/scripts/seed_interview_ar_jammal_agent.py` | Egyptian Arabic agent Jammal | `python scripts/seed_interview_ar_jammal_agent.py` |
| `voxbulk-api/scripts/seed_interview_ar_sultan_agent.py` | Gulf Arabic interview agent Sultan | `python scripts/seed_interview_ar_sultan_agent.py` |
| `voxbulk-api/scripts/seed_interview_gb_leo.py` | Legacy wrapper for regional agents | `python scripts/seed_interview_gb_leo.py` |
| `voxbulk-api/scripts/seed_interview_regional_agents.py` | 12 regional interview voice agents | `python scripts/seed_interview_regional_agents.py` |
| `voxbulk-api/scripts/seed_sales_ai_survey_agent.py` | Sales AI survey demo agent (used by seed-sales-demo.sh) | `python scripts/seed_sales_ai_survey_agent.py` |
| `voxbulk-api/scripts/seed_sales_demo.py` | Salesman workspace demo (20 interviews, WA + phone surveys, feedback QR) | `python -m scripts.seed_sales_demo --email EMAIL [--reset]` |
| `voxbulk-api/scripts/seed_survey_gb_agents.py` | GB phone survey voice agents | `python scripts/seed_survey_gb_agents.py` |
| `voxbulk-api/scripts/seed_utility_templates_to_db.py` | Import utility-safe seed MD into DB before UTILITY migration phases. | `python scripts/seed_utility_templates_to_db.py --help` |
| `voxbulk-api/scripts/seed_wa_survey_all_industries_from_md.py` | All WA industries from master MD | `python scripts/seed_wa_survey_all_industries_from_md.py --help` |
| `voxbulk-api/scripts/seed_wa_survey_all_industries_from_md.sh` | seed wa survey all industries from md | `bash voxbulk-api/scripts/seed_wa_survey_all_industries_from_md.sh` |
| `voxbulk-api/scripts/seed_wa_survey_from_md.py` | WA survey types from Markdown file | `python scripts/seed_wa_survey_from_md.py --help` |
| `voxbulk-api/scripts/seed_wa_survey_from_md.sh` | seed wa survey from md | `bash voxbulk-api/scripts/seed_wa_survey_from_md.sh` |
| `voxbulk-api/scripts/seed_wa_survey_industries.py` | WA survey industries + tags | `python scripts/seed_wa_survey_industries.py --help` |
| `voxbulk-api/scripts/seed_wa_survey_industries.sh` | seed wa survey industries | `bash voxbulk-api/scripts/seed_wa_survey_industries.sh` |
| `voxbulk-api/scripts/seed_wa_survey_test_pack.py` | WA survey test pack (no OpenAI) | `python scripts/seed_wa_survey_test_pack.py --help` |

### Deploy & VPS (scripts/) (35)

| Path | Description | Example command |
|------|-------------|-----------------|
| `scripts/_vps_ats_check.py` | VPS ATS check | `python scripts/_vps_ats_check.py` |
| `scripts/_vps_ats_check2.py` | VPS ATS check v2 | `python scripts/_vps_ats_check2.py` |
| `scripts/_vps_deploy.py` | Internal deploy helper | `used by deploy scripts` |
| `scripts/dev-api.mjs` | Start API (npm hook) | `npm run dev:api` |
| `scripts/e2e_local_test.ps1` | Windows local e2e | `powershell scripts/e2e_local_test.ps1` |
| `scripts/frontend-smoke.mjs` | Frontend smoke | `npm run smoke:frontend` |
| `scripts/generate-command-list.py` | Regenerate this command list (MD + HTML) | `python scripts/generate-command-list.py` |
| `scripts/lib/vps-frontend-perms.sh` | vps-frontend-perms.sh | `bash scripts/lib/vps-frontend-perms.sh` |
| `scripts/lib/vps-git-sync.sh` | Git sync helper (sourced by deploy) | `internal` |
| `scripts/regenerate-command-list-pdf.ps1` | Regenerate COMMAND-LIST.pdf from HTML | `powershell scripts/regenerate-command-list-pdf.ps1` |
| `scripts/retry-pending-voice-notes.sh` | Retry pending voice notes | `bash scripts/retry-pending-voice-notes.sh` |
| `scripts/run-celery-beat.sh` | Local Celery beat | `bash scripts/run-celery-beat.sh` |
| `scripts/run-celery-worker.sh` | Local Celery worker | `bash scripts/run-celery-worker.sh` |
| `scripts/sync-brand-assets.mjs` | Sync brand logos (prebuild hook) | `auto via npm prebuild` |
| `scripts/verify-billing-deploy.sh` | Billing post-deploy health | `bash scripts/verify-billing-deploy.sh` |
| `scripts/verify-unified-pricing.py` | Pricing sanity check | `python scripts/verify-unified-pricing.py` |
| `scripts/verify_wa_survey_local.py` | Local WA survey verify | `python scripts/verify_wa_survey_local.py` |
| `scripts/vps-check-auth-env.sh` | Check auth env vars | `bash scripts/vps-check-auth-env.sh` |
| `scripts/vps-deploy-f290115-verify.sh` | Legacy deploy verify | `bash scripts/vps-deploy-f290115-verify.sh` |
| `scripts/vps-deploy-production.sh` | Production deploy variant | `bash scripts/vps-deploy-production.sh` |
| `scripts/vps-finance-smoke.sh` | Finance release smoke | `bash scripts/vps-finance-smoke.sh` |
| `scripts/vps-finish-rollback-deploy.sh` | Finish rollback deploy | `bash scripts/vps-finish-rollback-deploy.sh` |
| `scripts/vps-fix-database-env.sh` | Fix DB env on VPS | `bash scripts/vps-fix-database-env.sh` |
| `scripts/vps-install-microsoft-well-known-nginx.sh` | Microsoft well-known nginx | `bash scripts/vps-install-microsoft-well-known-nginx.sh` |
| `scripts/vps-recover-api.sh` | Recover crashed API | `bash scripts/vps-recover-api.sh` |
| `scripts/vps-setup-celery.sh` | Install Celery worker + beat on VPS | `sudo bash scripts/vps-setup-celery.sh` |
| `scripts/vps-sync-all-ui.sh` | Sync all UI builds to wwwroot | `bash scripts/vps-sync-all-ui.sh` |
| `scripts/vps-sync-dashboard.sh` | Rsync dashboard to wwwroot | `bash scripts/vps-sync-dashboard.sh` |
| `scripts/vps-test-wa-survey-create.sh` | WA survey create test | `bash scripts/vps-test-wa-survey-create.sh` |
| `scripts/vps-update-ui.sh` | Rebuild UI only | `bash scripts/vps-update-ui.sh` |
| `scripts/vps-verify-dashboard.sh` | Dashboard wwwroot verify | `bash scripts/vps-verify-dashboard.sh` |
| `scripts/vps-verify-deploy.sh` | General deploy verify | `bash scripts/vps-verify-deploy.sh` |
| `scripts/vps-workflow-smoke.sh` | Workflow smoke (API + UI) | `bash scripts/vps-workflow-smoke.sh` |
| `scripts/write-admin-build-info.mjs` | Admin build metadata | `auto via npm prebuild` |
| `scripts/write-dashboard-build-info.mjs` | Dashboard build metadata | `auto via npm prebuild` |

### Test / smoke (9)

| Path | Description | Example command |
|------|-------------|-----------------|
| `voxbulk-api/scripts/e2e_interview_workflow_test.py` | End-to-end interview workflow functional test (run on VPS or locally). | `python scripts/e2e_interview_workflow_test.py --help` |
| `voxbulk-api/scripts/e2e_interview_workflow_test.sh` | e2e interview workflow test | `bash voxbulk-api/scripts/e2e_interview_workflow_test.sh` |
| `voxbulk-api/scripts/send_booking_confirm_email_test.py` | Send one interview_booking_confirm email (same template path as after candidate books). | `python scripts/send_booking_confirm_email_test.py --help` |
| `voxbulk-api/scripts/send_interview_invite_email_test.py` | Send one interview_booking_invite via CareerEmailService (same path as launch). | `python scripts/send_interview_invite_email_test.py --help` |
| `voxbulk-api/scripts/send_invites_for_order_test.py` | Run send_invites for one order (same path as dashboard launch). | `python scripts/send_invites_for_order_test.py --help` |
| `voxbulk-api/scripts/test_interview_email_lifecycle.py` | Send every interview lifecycle email to one inbox and (optionally) verify arrival. | `python scripts/test_interview_email_lifecycle.py --help` |
| `voxbulk-api/scripts/verify_wa_telnyx_push_deploy.sh` | verify wa telnyx push deploy | `bash voxbulk-api/scripts/verify_wa_telnyx_push_deploy.sh` |
| `voxbulk-api/scripts/verify_wa_utility_waba.py` | Verify Telnyx integration WABA matches the expected Voxbulk Ltd WABA for UTILITY migration. | `python scripts/verify_wa_utility_waba.py --help` |
| `voxbulk-api/scripts/workflow_smoke_test.py` | VoxBulk workflow smoke — API routes, email readiness, UI pages, and optional live auth. | `python scripts/workflow_smoke_test.py --help` |

### WhatsApp / Telnyx (36)

| Path | Description | Example command |
|------|-------------|-----------------|
| `voxbulk-api/scripts/audit_interview_email_templates.py` | Verify interview email flows point at the correct repo template keys. | `python scripts/audit_interview_email_templates.py --help` |
| `voxbulk-api/scripts/audit_wa_survey_templates.py` | Audit and repair all WA Survey WhatsApp templates — sync Telnyx, fix drafts, push, refresh status. | `python scripts/audit_wa_survey_templates.py --help` |
| `voxbulk-api/scripts/audit_wa_template_db.py` | Full DB audit for WA UTILITY migration — duplicates, orphans, missing AR pairs. | `python scripts/audit_wa_template_db.py --help` |
| `voxbulk-api/scripts/build_wa_survey_master_md.py` | Build master Markdown file from WA_SURVEY_ABC_CATALOG. | `python scripts/build_wa_survey_master_md.py --help` |
| `voxbulk-api/scripts/bulk_generate_wa_survey_library_templates.py` | Bulk-generate normal WA Survey library templates (one per industry survey type). | `python scripts/bulk_generate_wa_survey_library_templates.py --help` |
| `voxbulk-api/scripts/check_wa_template_row.py` | Read-only soft check for a WA survey template row (run on VPS). | `python scripts/check_wa_template_row.py --help` |
| `voxbulk-api/scripts/expand_wa_utility_template_seeds.py` | Expand WA Survey + Feedback seed catalogs to 25 utility-safe topics per industry. | `python scripts/expand_wa_utility_template_seeds.py --help` |
| `voxbulk-api/scripts/export_wa_template_baseline.py` | Export baseline WA template inventory (survey + feedback) for migration diff. | `python scripts/export_wa_template_baseline.py --help` |
| `voxbulk-api/scripts/export_wa_templates_industry_map.py` | export wa templates industry map | `python scripts/export_wa_templates_industry_map.py --help` |
| `voxbulk-api/scripts/link_wa_survey_templates_from_telnyx.py` | Link local survey WA template rows to existing Telnyx/Meta templates by name. | `python scripts/link_wa_survey_templates_from_telnyx.py --help` |
| `voxbulk-api/scripts/list_wa_not_pushed.py` | List buttoned WA Survey templates not APPROVED/PENDING on Meta. | `python scripts/list_wa_not_pushed.py --help` |
| `voxbulk-api/scripts/migrate_wa_templates_utility.py` | OpenAI 4-phase WA UTILITY migration — rewrite DB templates, save, push to Meta. | `python scripts/migrate_wa_templates_utility.py --help` |
| `voxbulk-api/scripts/migrate_wa_templates_utility.sh` | migrate wa templates utility | `bash voxbulk-api/scripts/migrate_wa_templates_utility.sh` |
| `voxbulk-api/scripts/provision_interview_telnyx_assistants.py` | Create or sync Telnyx assistants for English regional interview agents. | `python scripts/provision_interview_telnyx_assistants.py --help` |
| `voxbulk-api/scripts/push_all_feedback_to_meta_overnight.py` | Overnight batch push: all Customer Feedback industries to Meta (safe rate limits) | `python -u scripts/push_all_feedback_to_meta_overnight.py --batch-size 5 --delay-sec 15` |
| `voxbulk-api/scripts/push_feedback_industry_to_telnyx.py` | Push all Customer Feedback templates for ONE industry to Meta (no batch delay) | `python scripts/push_feedback_industry_to_telnyx.py --industry-slug fitness` |
| `voxbulk-api/scripts/push_feedback_industry_to_telnyx.sh` | push feedback industry to telnyx | `bash voxbulk-api/scripts/push_feedback_industry_to_telnyx.sh` |
| `voxbulk-api/scripts/push_feedback_template_to_telnyx.py` | Push one Customer Feedback template to Meta | `python scripts/push_feedback_template_to_telnyx.py --help` |
| `voxbulk-api/scripts/push_feedback_template_to_telnyx.sh` | push feedback template to telnyx | `bash voxbulk-api/scripts/push_feedback_template_to_telnyx.sh` |
| `voxbulk-api/scripts/push_force_update_wa_templates_batch.py` | Force-push local WA survey template drafts to Meta (same name, content update). | `python scripts/push_force_update_wa_templates_batch.py --help` |
| `voxbulk-api/scripts/push_force_update_wa_templates_batch.sh` | push force update wa templates batch | `bash voxbulk-api/scripts/push_force_update_wa_templates_batch.sh` |
| `voxbulk-api/scripts/push_wa_one_verbose.py` | Push one WA Survey template to Meta with full error detail. | `python scripts/push_wa_one_verbose.py --help` |
| `voxbulk-api/scripts/push_wa_survey_templates_to_telnyx.py` | Push WA Survey WhatsApp templates to Telnyx/Meta (CLI — no admin UI required). | `python scripts/push_wa_survey_templates_to_telnyx.py --help` |
| `voxbulk-api/scripts/push_wa_survey_templates_to_telnyx.sh` | push wa survey templates to telnyx | `bash voxbulk-api/scripts/push_wa_survey_templates_to_telnyx.sh` |
| `voxbulk-api/scripts/regenerate_survey_templates_context.py` | Regenerate existing WA Survey templates with OpenAI (local drafts only). | `python scripts/regenerate_survey_templates_context.py --help` |
| `voxbulk-api/scripts/repush_stuck_wa_utility_templates.py` | Fix templates stuck with Meta 2388024: link if possible, else rename and push fresh. | `python scripts/repush_stuck_wa_utility_templates.py --help` |
| `voxbulk-api/scripts/retry_wa_utility_migration_failures.py` | Retry failed templates from a migration-phaseN-*.json report. | `python scripts/retry_wa_utility_migration_failures.py --help` |
| `voxbulk-api/scripts/rewrite_wa_survey_templates_for_utility.py` | Rewrite WA survey templates for Meta UTILITY (Feedback Survey) and optionally push via Telnyx. | `python scripts/rewrite_wa_survey_templates_for_utility.py --help` |
| `voxbulk-api/scripts/rewrite_wa_survey_templates_for_utility.sh` | rewrite wa survey templates for utility | `bash voxbulk-api/scripts/rewrite_wa_survey_templates_for_utility.sh` |
| `voxbulk-api/scripts/run_wa_utility_migration_phase.sh` | run wa utility migration phase | `bash voxbulk-api/scripts/run_wa_utility_migration_phase.sh` |
| `voxbulk-api/scripts/sync_interview_email_templates.py` | Push latest interview email templates from code defaults into the database (VPS one-off). | `python scripts/sync_interview_email_templates.py --help` |
| `voxbulk-api/scripts/telnyx_sms_setup.py` | Configure Telnyx SMS for VoxBulk inbound (Meta verification codes, Admin Refresh inbound). | `python scripts/telnyx_sms_setup.py --help` |
| `voxbulk-api/scripts/translate_feedback_templates_to_ar.py` | Translate Customer Feedback templates to Arabic (OpenAI JSON API) and push to Telnyx. | `python scripts/translate_feedback_templates_to_ar.py --help` |
| `voxbulk-api/scripts/translate_feedback_templates_to_ar.sh` | translate feedback templates to ar | `bash voxbulk-api/scripts/translate_feedback_templates_to_ar.sh` |
| `voxbulk-api/scripts/wa_not_pushed_lib.py` | Shared helpers for list/diagnose/fix WA survey templates not on Meta (buttoned only). | `python scripts/wa_not_pushed_lib.py --help` |
| `voxbulk-api/scripts/watch_wa_migration_progress.py` | Live DB progress for a WA UTILITY migration phase (works while migrate script runs). | `python scripts/watch_wa_migration_progress.py --help` |

### Interview / voice (2)

| Path | Description | Example command |
|------|-------------|-----------------|
| `voxbulk-api/scripts/apply_interview_voice_matrix.py` | Apply accent-appropriate voices to English interview Telnyx assistants. | `python scripts/apply_interview_voice_matrix.py --help` |
| `voxbulk-api/scripts/vps_interview_audit.py` | VPS interview workflow + config audit. Run on the server after deploy: | `python scripts/vps_interview_audit.py --help` |

### Diagnose (8)

| Path | Description | Example command |
|------|-------------|-----------------|
| `voxbulk-api/scripts/diagnose_interview_invite.py` | Explain why an interview's invitation email did or did not send — READ ONLY. | `python scripts/diagnose_interview_invite.py --help` |
| `voxbulk-api/scripts/diagnose_interview_voice.py` | Inspect the interview voice agent's language/voice/greeting — READ ONLY. | `python scripts/diagnose_interview_voice.py --help` |
| `voxbulk-api/scripts/diagnose_smtp_delivery.py` | Inspect SMTP transport + last invite send for an interview (no send). | `python scripts/diagnose_smtp_delivery.py --help` |
| `voxbulk-api/scripts/diagnose_stt_providers.py` | One-off STT provider diagnostic for production. | `python scripts/diagnose_stt_providers.py --help` |
| `voxbulk-api/scripts/diagnose_user_interviews.py` | List interview orders for a dashboard user — phone vs web sessions. READ ONLY. | `python scripts/diagnose_user_interviews.py --help` |
| `voxbulk-api/scripts/diagnose_wa_push_failures.py` | Diagnose buttoned WA Survey templates not on Meta — group errors by bucket. | `python scripts/diagnose_wa_push_failures.py --help` |
| `voxbulk-api/scripts/diagnose_wa_template_push.py` | Show what would be sent to Telnyx/Meta for a WA Survey template (no API call). | `python scripts/diagnose_wa_template_push.py --help` |
| `voxbulk-api/scripts/diagnose_wa_template_push.sh` | diagnose wa template push | `bash voxbulk-api/scripts/diagnose_wa_template_push.sh` |

### Repair / cleanup (18)

| Path | Description | Example command |
|------|-------------|-----------------|
| `voxbulk-api/scripts/backfill_feedback_survey_config.py` | Rebuild survey_config_json for Customer Feedback locations from flags + selected topics. | `python scripts/backfill_feedback_survey_config.py --help` |
| `voxbulk-api/scripts/backfill_interview_session_usage.py` | Backfill usage_metered_at for completed web/phone interview sessions missing plan metering. | `python scripts/backfill_interview_session_usage.py --help` |
| `voxbulk-api/scripts/cleanup_legacy_interview_agents.py` | Find or deactivate legacy duplicate interview agents (non-canonical slugs). | `python scripts/cleanup_legacy_interview_agents.py --help` |
| `voxbulk-api/scripts/cleanup_wa_survey_template_links.py` | Remove mistaken survey_type_templates links (templates synced onto wrong survey types). | `python scripts/cleanup_wa_survey_template_links.py --help` |
| `voxbulk-api/scripts/cleanup_wa_survey_templates.py` | Delete WA Survey templates outside Global System Templates + Hospitality & food. | `python scripts/cleanup_wa_survey_templates.py --help` |
| `voxbulk-api/scripts/cleanup_wa_survey_utility_duplicates.py` | Clean duplicate WA survey templates on Meta: retire old *_abc_*, resubmit REJECTED *_utu_*. | `python scripts/cleanup_wa_survey_utility_duplicates.py --help` |
| `voxbulk-api/scripts/cleanup_wa_template_clone_rows.py` | One-time cleanup: merge duplicate parent/clone WA survey template rows into one active row. | `python scripts/cleanup_wa_template_clone_rows.py --help` |
| `voxbulk-api/scripts/clear_feedback_wa_state.py` | Cancel active Customer Feedback + legacy WA survey state for a test phone. | `python scripts/clear_feedback_wa_state.py --help` |
| `voxbulk-api/scripts/clear_feedback_wa_state.sh` | clear feedback wa state | `bash voxbulk-api/scripts/clear_feedback_wa_state.sh` |
| `voxbulk-api/scripts/clear_stale_telnyx_greetings.py` | Clear stale telnyx_greeting values and push build_agent_greeting() to Telnyx. | `python scripts/clear_stale_telnyx_greetings.py --help` |
| `voxbulk-api/scripts/finance_gc_backfill.py` | Report or backfill GoCardless subscriptions missing external_subscription_id. | `python scripts/finance_gc_backfill.py --help` |
| `voxbulk-api/scripts/fix_and_push_wa_templates.py` | Fix and push buttoned WA Survey templates per industry (buttonless excluded). | `python scripts/fix_and_push_wa_templates.py --help` |
| `voxbulk-api/scripts/fix_wa_survey_template_body_variables.py` | Fix WA Survey template BODY variables/examples in the database. | `python scripts/fix_wa_survey_template_body_variables.py --help` |
| `voxbulk-api/scripts/fix_wa_survey_template_body_variables.sh` | fix wa survey template body variables | `bash voxbulk-api/scripts/fix_wa_survey_template_body_variables.sh` |
| `voxbulk-api/scripts/repair_customer_feedback_subscriptions.py` | Repair Customer Feedback subscription tags, usage periods, and org module flags. | `python scripts/repair_customer_feedback_subscriptions.py --help` |
| `voxbulk-api/scripts/repair_unblock_wa_templates.py` | One-time repair: re-enable WA survey/feedback types and templates disabled by the hide/blocklist rollout. | `python scripts/repair_unblock_wa_templates.py --help` |
| `voxbulk-api/scripts/repair_wa_survey_template_drafts.py` | Repair WA Survey template drafts stored with invalid Meta BODY examples ([[]] or missing). | `python scripts/repair_wa_survey_template_drafts.py --help` |
| `voxbulk-api/scripts/repair_wa_survey_template_drafts.sh` | repair wa survey template drafts | `bash voxbulk-api/scripts/repair_wa_survey_template_drafts.sh` |

### Database (3)

| Path | Description | Example command |
|------|-------------|-----------------|
| `voxbulk-api/scripts/bootstrap_mysql.py` | Bootstrap an empty MySQL database from SQLAlchemy models, then stamp Alembic to head. | `python scripts/bootstrap_mysql.py --help` |
| `voxbulk-api/scripts/local_mysql_bootstrap.py` | Create local MySQL user/database from DATABASE_URL in .env (non-destructive by default). | `python scripts/local_mysql_bootstrap.py --help` |
| `voxbulk-api/scripts/setup-local-mysql.sql` | setup-local-mysql.sql | `see file` |

### Ops / utilities (5)

| Path | Description | Example command |
|------|-------------|-----------------|
| `voxbulk-api/scripts/_ensure_system_tpls.py` |  ensure system tpls | `python scripts/_ensure_system_tpls.py --help` |
| `voxbulk-api/scripts/_run_all_regen_batches.py` | Run all survey template regen batches with --save (local only). | `python scripts/_run_all_regen_batches.py --help` |
| `voxbulk-api/scripts/extract_legal_defaults.py` | extract legal defaults | `python scripts/extract_legal_defaults.py --help` |
| `voxbulk-api/scripts/generate_hubspot_test_import_xlsx.py` | Generate HubSpot test import Excel (local file only — not committed). | `python scripts/generate_hubspot_test_import_xlsx.py --help` |
| `voxbulk-api/scripts/sanitize_production_env.py` | Deduplicate voxbulk-api/.env and drop template placeholder values. | `python scripts/sanitize_production_env.py --help` |

### Frontend build hooks (2)

| Path | Description | Example command |
|------|-------------|-----------------|
| `dashboard.voxbulk.com/dashboard-web/scripts/sync-integration-logos.mjs` | Sync integration logos (dashboard prebuild hook) | `auto via npm prebuild` |
| `voxbulk.com/frontend/scripts/fix-preview-server.mjs` | Fix Vite preview host check (voxbulk.com allowedHosts) | `node voxbulk.com/frontend/scripts/fix-preview-server.mjs` |

---

## LOCAL DEV (Windows)

```powershell
cd c:\Users\zaghlol\Downloads\voxbulk.com
npm run dev              # API + public + admin
npm run dev:api

cd voxbulk-api
.\.venv\Scripts\Activate.ps1
alembic upgrade head
uvicorn main:app --reload --host 0.0.0.0 --port 8000

cd dashboard.voxbulk.com\dashboard-web
npm run dev              # port 5175
```

## GIT

```bash
git pull origin main
git push origin main
```

Remote: `https://github.com/menasimuk-hub/Vox-new.git` branch `main`
