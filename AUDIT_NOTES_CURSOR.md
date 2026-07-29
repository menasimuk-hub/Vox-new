# AUDIT_NOTES_CURSOR.md — Phase 2 (audit only)

Inspection notes from the Phase 1 security pass. **No code changes** for these items unless a later task explicitly asks.

## A) Router duplication in `voxbulk-api/main.py`

Several routers are registered twice: once bare and once with `prefix="/api"` (examples: `legal_pages_router`, `promo_offers_router`, `frontpage_router`, `blog_news_router`, `admin_frontpage_router`, `admin_blog_news_router`, `admin_seo_router`, `public_seo_router`, `admin_meeting_room_router`, `knowledge_base_router`, `admin_partners_router`, `partner_v1_router`, `admin_ai_team_router`, `public_ai_team_router`, `admin_products_router`, `admin_pricing_router`, `admin_sales_reps_router`).

Those routers already define their own path prefixes (e.g. `/frontpage`, `/admin/seo`, `/partner/v1`).

Admin nginx strips `/api` before proxying to uvicorn (`docs/nginx-admin.voxbulk.com.conf`: `rewrite ^/api/(.*)$ /$1`). The dual mounts therefore look like **intentional path compatibility** (clients hitting `/api/...` on a host that does not strip the prefix, vs production admin which does).

**Verdict:** Do not remove either mount without proving no client/nginx path still needs `/api/...` on the API process.

## B) Billing overage consent

| Piece | Finding |
|-------|---------|
| Flag | `Organisation.allow_overage` (`voxbulk-api/app/models/organisation.py`) — **defaults to `True`** |
| Customer toggle | `PATCH` billing overage in `app/routers/billing.py` (`set_customer_overage`) |
| Admin toggle | `OrgControlCenterActionsService.set_allow_overage` |
| Settlement | `CampaignBillingSettlementService.settle_order` / `_issue_completion_invoice` / `_sync_overage_invoiced` — **do not read `allow_overage`** |
| Launch | Survey/interview eligibility can set `mode` to `subscription_overage` / `subscription_phone_overage` **without** checking the flag |
| Enforced | `feedback_ai_followup_service.py` (~line 363) blocks AI follow-up when overage disabled and no minutes remain |
| Retired | `UsageWalletService.maybe_invoice_overage` returns `None` (period rollover no longer invoices overage) |

**Confirmed gap:** overage-related completion invoices / DD collection can proceed even when `allow_overage` is `False`, and new orgs get overage allowed by default without an explicit consent step.

**Suggested fix (not implemented):**
1. Gate launch overage modes on `org.allow_overage is True`.
2. Gate settlement charges that represent overage on the same flag (or refuse settlement charge and fail closed).
3. Product decision: whether new orgs should default `allow_overage=False` (schema/default change).

## C) Utility scripts

### `voxbulk-api/get_api_key.py`
- Reads sqlite `dev.db` and **prints** `telnyx_api_key` to stdout.
- Secret-exposing local debug helper; not production-safe; not wired into app startup.
- Candidate to delete or move under `scripts/` and stop printing raw keys.

### `voxbulk-api/fix_telnyx_template.py`
- One-off ops script: loads Telnyx key from DB settings, lists/deletes `interview_email_sent` on Telnyx if body still has `{{4}}`.
- Does not print the API key, but mutates the provider account.
- Ops-only; not for production boot paths. Leave as-is unless cleaning repo root of ad-hoc scripts.

## D) Seed directories

| Path | Role |
|------|------|
| `voxbulk-api/seed-data/` | Markdown/text sources and migration/push reports (customer-feedback, wa-survey, wa-templates). Used by many scripts and some services via filesystem paths. |
| `voxbulk-api/seed_data/` | Importable Python package (`wa_survey_abc_catalog`, naming helpers, etc.) used by app services and scripts via `from seed_data...`. |

**Verdict:** Complementary, **both required** — not duplicates of each other.
