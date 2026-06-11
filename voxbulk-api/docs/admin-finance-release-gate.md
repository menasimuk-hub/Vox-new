# VoxBulk Admin Finance — Release Gate

**Scope:** Admin finance rollout for billing, refunds, wallet ledger, tax/VAT, cancellation handling, upgrade preview, and finance visibility.  
**Audience:** Engineering, finance ops, release owner.  
**Rollout target:** Staged production rollout for accountant/superadmin users only.  
**Branch:** `fix/admin-finance-hardening`

## Release decision

**Go only if every red gate below passes.**  
If any red gate fails, do not release finance ops broadly.

---

## Red gates

### 1. Production migration gate

`0117_billing_finance_foundation` must be applied on production MySQL before API deploy.

- `alembic current` must show revision `0117_billing_finance_foundation` on staging and production.
- API and Celery worker must be restarted after migration.

**Block release if:**

- production is not on migration 0117,
- new subscription/payment_event columns are missing,
- Celery is still running against pre-migration schema.

**Status:** BLOCK until ops confirms on staging and production.

---

### 2. Finance access control gate

Accountant can access:

- `/billing/refunds`
- `/billing/payment-events`
- `/billing/wallet-ledger`
- `/billing/exceptions`
- `/billing/tax`

Technical/support/marketing users must be blocked in both UI and API. Backend must return 403 for blocked roles on finance endpoints.

**Block release if:**

- a non-finance role can access finance pages or finance APIs,
- accountant cannot access any required finance page or endpoint.

**Status:** Code ready — confirm on staging smoke.

---

### 3. Wallet ledger integrity gate

`POST /admin/organisations/{id}/wallet/credit` must create: `WalletTransaction`, audit event, `wallet.credit` PaymentEvent.

OCC wallet debit must create: ledger row, audit event, `wallet.debit` PaymentEvent.

Organisation wallet balance must match the latest ledger `balance_after_minor`.

**Block release if:**

- wallet balance changes without ledger entry,
- audit/event logging is missing on wallet finance actions,
- visible wallet balance disagrees with ledger state.

**Status:** Code ready — confirm on staging smoke.

---

### 4. Refund workflow gate

Approving a wallet refund review must: increase wallet balance exactly once, complete the review, create `refund.completed` event.

Rejecting a refund must: create no wallet credit, emit `refund.rejected` event.

Stripe external refund failure must: move review to `failed`, emit `refund.failed` event.

**Known limitation (accepted for staged rollout):** GoCardless/Airwallex external refund automation is not end-to-end; manual admin bookkeeping is still required.

**Block release if:**

- duplicate refund credits are possible,
- refund success/failure paths do not emit auditable events,
- Stripe failure can silently fail.

**Status:** Code ready — confirm on staging smoke.

---

### 5. Cancellation finalization gate

Scheduling cancel with `wallet_credit` must preserve end-of-period visibility:

- next billing date shows period end,
- next charge displays **"No renewal (cancel scheduled)"**.

After period close/finalize, unused value must either credit wallet or emit explicit failure event (e.g. `wallet.cancellation_credit_failed`).

Scheduling cancel with `payment_method_refund` must not auto-credit wallet at period end.

**Block release if:**

- cancellation hides renewal/period-end state,
- period-end credit fails without explicit event/audit visibility,
- payment-method refund requests are auto-credited to wallet incorrectly.

**Status:** Code ready — confirm on staging smoke.

---

### 6. Tax snapshot gate

Subscription finance snapshot must use ISO country code (e.g. `GB`), not truncated free-text country.

`tax_rate_percent` must populate from effective VAT logic.

TaxAdmin VAT changes must be reflected after finance sync/renewal.

**Block release if:**

- tax country code is wrong,
- tax rate remains missing when VAT should apply,
- tax page changes do not affect subscription finance state.

**Status:** Code ready — confirm on staging smoke.

---

### 7. Next charge / upgrade preview gate

Billing subscriptions table must show renewal visibility for active and cancel-scheduled subscriptions.

OrganisationProfile and OCC plan change flow must show upgrade preview before confirm.

Preview must return a usable prorated amount and monthly display.

**Known limitations (accepted for staged rollout):**

- pro-rata uses a fixed 30-day assumption,
- downgrade preview returns 0,
- preview is ex-VAT.

**Block release if:**

- next charge is blank or misleading for active/cancel-scheduled subscriptions,
- upgrade preview UI is missing where admins change plans.

**Status:** Code ready — confirm on staging smoke.

---

### 8. Non-GBP pricing gate

EUR orgs must show correct next charge and upgrade preview amounts using actual plan pricing, not GBP fallback.

Currency-aware formatting must be present on active finance surfaces used in rollout.

**Block release if:**

- EUR orgs fall back to GBP plan values in active billing flows,
- finance-critical pages display materially wrong currency/amounts.

**Status:** BLOCK until EUR `PlanPrice` rows are verified for in-scope plans on staging/production. Waive only if rollout is explicitly GBP-only.

---

## Remaining red gates summary (pre-deploy)

| Gate | Blocker? | Action |
|------|----------|--------|
| 1 Migration 0117 | **YES** | Run migration; verify `alembic current`; restart API + Celery |
| 2 Access control | No (code) | Staging smoke: accountant OK, technical 403 |
| 3 Wallet ledger | No (code) | Staging smoke: credit/debit + balance match |
| 4 Refunds | No (code) | Staging smoke: approve/reject/Stripe fail |
| 5 Cancellation | No (code) | Staging smoke: schedule + finalize paths |
| 6 Tax snapshot | No (code) | Staging smoke: GB code + VAT rate |
| 7 Upgrade preview | No (code) | Staging smoke: Profile + OCC preview |
| 8 EUR pricing | **YES** (if EUR in scope) | Verify PlanPrice EUR rows; smoke EUR org |

**Overall:** NO-GO until Gate 1 is green. Gate 8 required if EUR organisations are in rollout scope.

---

## Staged rollout constraints

Even if all red gates pass, limit rollout to:

- accountant users,
- superadmin users,
- monitored rollout only.

Do not treat this as fully unattended finance automation until provider refund coverage and reporting depth are expanded.

---

## Staging smoke checklist

```
[ ] alembic current → 0117 (staging)
[ ] Accountant: /billing/refunds, /payment-events, /wallet-ledger, /exceptions, /tax
[ ] Technical: same URLs blocked (UI + API 403)
[ ] POST wallet credit → WalletTransaction + audit + wallet.credit PaymentEvent
[ ] OCC wallet debit → ledger + wallet.debit PaymentEvent
[ ] Balance == latest ledger balance_after_minor
[ ] Approve refund → single credit + refund.completed event
[ ] Reject refund → no credit + refund.rejected event
[ ] Schedule cancel (wallet_credit) → period end + "No renewal (cancel scheduled)"
[ ] Finalize → credit OR wallet.cancellation_credit_failed event
[ ] Schedule cancel (payment_method_refund) → no auto wallet credit
[ ] tax_country_code = ISO (e.g. GB)
[ ] Upgrade preview in Profile + OCC
[ ] EUR org (if in scope): amounts in EUR, not GBP fallback
```

**Production-prep:** repeat migration check + smoke on one safe org after API/Celery restart.

---

## Sign-off

| Role | Gate 1 | Gates 2–7 (staging) | Gate 8 (EUR scope) | Staged rollout OK |
|------|--------|----------------------|--------------------|-------------------|
| Engineering | ☐ | ☐ | ☐ | ☐ |
| Finance ops | — | ☐ | ☐ | ☐ |
| Release owner | ☐ | ☐ | ☐ | ☐ |
