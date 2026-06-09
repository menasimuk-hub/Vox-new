# VoxBulk Billing System — Build Report

**Branch:** `feature/billing-system`  
**Date:** June 2026  
**Scope:** Full 3-phase billing system (foundation, lifecycle, access control)

---

## Executive summary

VoxBulk now has an end-to-end B2B billing stack:

- **PAYG** customers top up via **Stripe / Airwallex** and pay launches from the **wallet only**
- **Subscribers** use **plan allowance → wallet → GoCardless Direct Debit** at launch
- **Invoices** use sequential INV numbering, VAT (UK when configured), PDF, and email
- **Lifecycle** covers reconciliation refunds, DD recovery, disputes, monthly fees, and pro-rata upgrades
- **Access control** blocks launches when credit limits, mandates, or past-due invoices apply

---

## Phase 1 — Core billing foundation

### Removed
- Per-order GoCardless redirect checkout
- Legacy FX multipliers and `ServicePricingRule` catalog quoting
- Dental default plan seed / platform catalog quote paths for surveys

### Added
| Area | Details |
|------|---------|
| **Data** | Migration `0109`: `plan_prices`, `wallet_transactions`, `billing_settings`, `credit_notes`, invoice DD fields, mandate fields |
| **Pricing** | `PlanPriceService` — explicit GBP/USD/CAD/AUD rates per plan |
| **Wallet** | Ledger + Stripe/Airwallex PaymentIntents + dashboard top-up UI |
| **Launch** | `LaunchBillingService` — allowance → wallet → DD orchestration |
| **Invoices** | Sequential numbering, VAT, PDF, email via `InvoiceService` |
| **Admin** | Stripe, Airwallex, GoCardless integrations; plan prices; invoice settings |
| **Dashboard** | Wallet top-up, launch billing modal, billing page |

---

## Phase 2 — Billing lifecycle

| Feature | Implementation |
|---------|----------------|
| **Campaign reconciliation** | `BillingReconciliationService` — refunds unused charges to wallet + credit note on complete/cancel |
| **Monthly subscription billing** | Celery `billing.process_monthly_subscriptions` — INV invoice + DD + email each period |
| **DD recovery** | Webhook + Celery `billing.retry_failed_dd_payments` — 3 retries over ~7 days, then `past_due` |
| **Disputes** | Admin flag/clear; pauses DD retries |
| **Usage emails** | 80% and 100% allowance warnings |
| **Allowance reset** | `rollover_due_periods` resets warnings and opens new periods on billing anchor |
| **Pro-rata upgrades** | `BillingLifecycleService.change_subscription_plan` — DD charge for mid-cycle upgrade; downgrade at next cycle |
| **Admin tools** | Bank refund logging, manual wallet credit |

---

## Phase 3 — Access control and compliance

| Feature | Implementation |
|---------|----------------|
| **Credit limit** | `BillingAccessService` — blocks launch when outstanding invoices exceed `org.credit_limit_minor` |
| **Mandate cancelled** | GoCardless `mandates` webhook → block launches, email customer + admin |
| **First payment** | Bacs = immediate access; ACH/PAD/BECS = `pending_first_payment` (DD launches blocked, wallet/allowance OK) |
| **First payment failure** | Suspend within 7-day grace on failed DD |
| **Customer portal** | `/billing/access`, invoices list/PDF, wallet history, usage meters (dashboard Account → Billing) |
| **Admin invoices** | Dispute, resolve, bank refund, DD retry indicators on `InvoicesAdmin` |

---

## Launch billing decision tree

```
Launch clicked
    → Credit limit / mandate / past-due check (Phase 3)
    → Estimate from plan_prices
    → Allowance covers all? → Launch free
    → Wallet covers (PAYG)? → Debit wallet → Launch
    → Subscriber overage? → Confirm DD → Invoice + mandate payment → Launch
    → Insufficient wallet (PAYG)? → Block + top-up prompt
```

---

## Celery scheduled tasks

| Task | Schedule | Purpose |
|------|----------|---------|
| `billing.rollover_usage_periods` | Daily | Close periods, invoice overage, reset allowance |
| `billing.process_monthly_subscriptions` | Hourly | Plan fee invoice + DD |
| `billing.retry_failed_dd_payments` | Hourly | Retry failed DD collections |

Timezone: UTC (existing Celery config).

---

## Key API endpoints

### Customer (`/billing`)
- `GET /access` — launch blockers and credit summary
- `GET /wallet`, `POST /wallet/topup/*` — balance and top-up
- `GET /invoices`, `GET /invoices/{id}/pdf` — invoice portal
- `GET /usage-summary` — allowance vs usage

### Admin (`/admin/billing`)
- Invoice list/filter, dispute, resolve, bank refund, resend email
- `POST /organisations/{id}/wallet-credit` — manual wallet credit
- Provider settings (Stripe, Airwallex, GoCardless)
- Plan prices, currency rates, invoice settings

---

## Tests

Billing-focused pytest modules (all passing):

- `test_survey_payment_flow.py` — PAYG wallet launch
- `test_billing_lifecycle.py` — reconciliation, DD recovery, disputes, monthly billing
- `test_billing_access.py` — credit limit, mandate, first payment
- `test_gocardless_billing_webhook.py` — payment webhooks
- `test_usage_metering.py` — 80%/100% usage emails

---

## Deployment notes

1. Run migration: `alembic upgrade head` (includes `0109_billing_system_foundation`)
2. Configure admin: Stripe, Airwallex, GoCardless keys; billing settings (company, VAT, invoice prefix)
3. Seed plan prices per currency in Admin → Pricing
4. Restart Celery worker + beat to pick up new billing tasks
5. Set org `credit_limit_minor` where per-customer limits apply (0 = unlimited)

---

## Known follow-ups (non-blocking)

- Cancel GoCardless auto-subscription objects at GC after mandate setup (monthly billing is VoxBulk-controlled; GC subscription still created on signup for mandate linkage — migrate existing subs to drop GC recurring)
- `useSurveyPackages()` wizard path still references removed endpoint — replace with plan_prices display
- Full pytest suite has pre-existing failures outside billing (Telnyx mocks, docx, WA workflow)

---

## Commits on this branch

1. **Phase 1** — Core billing foundation  
2. **Phase 2** — Billing lifecycle  
3. **Phase 3** — Access control and compliance  
