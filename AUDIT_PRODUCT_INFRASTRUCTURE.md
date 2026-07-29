# Product/Package Infrastructure Audit
**Read-only analysis of pricing models, admin controls, and dashboard integration**
**Date: 2026-05-24**

---

## 1. PRODUCTS HUB / ADMIN PACKAGE SYSTEM

### Admin Pages That Exist
| Page | Path | Manages | Purpose |
|------|------|---------|---------|
| **Products Hub** | `/billing/products` | All products in unified view | Central control for subscriptions + campaign packs |
| **Plan Editor** | `/billing/products/plan/[id]/edit` | Individual subscription plan details | Edit name, price, features, marketing copy |
| **Services & Pricing** | `/billing/services-pricing` | Service pricing rules (Survey/Interview bundles) | Edit bundle sizes, per-person pricing, overage rates |
| **Packages & Pricing** | `/billing/packages-pricing` | Subscription plan marketing display | Update plan names, prices, descriptions, feature lists shown to customers |

### What Admin Can Create/Edit Today

#### A. **Subscription Plans** (`/billing/products/plan/edit`)
- Plan name
- Plan code (e.g. "starter", "practice", "group")
- Price (GBP pence)
- Monthly/yearly interval
- Service kind (all are "subscription")
- Calls included per month
- WhatsApp included per month
- SMS included per month
- Overage per minute (pence) — for calls past the included limit
- Marketing description
- Feature list (JSON array → displayed as bullet points)
- Active/inactive toggle
- **Duplicate plan** action

**Model:** `Plan` (`app/models/plan.py`)
```
id, code, name, price_gbp_pence, interval, description, features_json,
calls_included, whatsapp_included, sms_included, overage_per_min_pence,
is_active, sort_order, created_at, updated_at
```

**Endpoints:**
- `GET /admin/products/plans` — list all
- `POST /admin/products/plans` — create
- `GET /admin/products/plans/{id}` — read
- `PUT /admin/products/plans/{id}` — update
- `POST /admin/products/plans/{id}/duplicate` — copy
- `PATCH /admin/products/plans/{id}/active` — toggle active
- `DELETE /admin/products/plans/{id}` — remove

#### B. **Service Pricing Rules** (`/billing/services-pricing`)
**For Survey and Interview services only.** Each service can have multiple pricing rules by channel.

**Model:** `ServicePricingRule` (`app/models/platform_service.py`)
```
id, service_id, channel, rule_type, label, base_fee_pence, unit_price_pence,
bundle_size, bundle_price_pence, included_units, overage_unit_price_pence,
currency, is_active, sort_order, notes, created_at, updated_at
```

**Supported Fields:**
- `channel` (e.g. "base", "whatsapp", "call", "ai_call", "zoom")
- `rule_type` — one of:
  - `flat_per_order` — fixed fee for the whole order
  - `per_person` — charge × recipient count
  - `bundle` — charge per N-pack (e.g. 100 contacts at a time)
  - `flat_plus_per_person` — base fee + per-person charge
- `bundle_size` (optional) — e.g. 100 for bundle pricing
- `bundle_price_pence` — price of one bundle
- `included_units` (optional) — included units before overage applies
- `overage_unit_price_pence` (optional) — price if user goes over included units

**Default Survey Rules (hardcoded):**
```
Survey service (code: "survey"):
  - base channel, flat_per_order, £5 setup fee
  - whatsapp channel, bundle, 100 contacts @ £15
  - call channel, per_person, 18p per contact (AI call)

Interview service (code: "interview"):
  - ai_call channel, per_person, 350p per person
  - zoom channel, per_person, 500p per person
```

**Endpoints:**
- `GET /admin/platform-services` — list all services + rules
- `PUT /admin/platform-services/{id}` — update service metadata
- `POST /admin/platform-services/{id}/pricing-rules` — create rule
- `PUT /admin/platform-services/pricing-rules/{rule_id}` — update rule
- `POST /admin/platform-services/quote-preview` — calculate cost for hypothetical order

#### C. **Promo Credits** (mentioned but not fully in scope)
- Model: `PromoOffer` (can grant bundle discounts or free credits)
- Fields include `overage_per_min_pence` — user inherits this if promo applies

### What CANNOT Be Configured in Admin Yet
- ❌ **Separate subscription tiers for Survey bundles** (e.g. "Survey Lite, Pro, Enterprise") — Survey pricing is global via Service rules only
- ❌ **Different WhatsApp vs AI-call pricing for Survey per subscription tier**
- ❌ **Consent/approval flags for overage charges** — no checkbox field exists
- ❌ **Pay-as-you-go opt-in control** — system auto-invoices overage if overage_per_min_pence is set, no user consent captured

**File Paths:**
- Admin frontend: `admin.voxbulk.com/adim-web/src/pages/ProductsHub.jsx`, `ProductPlanEdit.jsx`, `ServicesPricing.jsx`
- Backend: `voxbulk-api/app/routers/admin_products.py`, `admin_platform_services.py`
- Services: `app/services/plan_admin_service.py`, `platform_catalog_service.py`

---

## 2. EXISTING PRICING MODELS IN BACKEND

### A. **Subscription Plans** (Monthly/Yearly)
**Purpose:** Define org billing cycle, included call/WhatsApp/SMS allowances, overage rate.

**Model:** `Plan`
```
- Defines pricing for whole month/year for an organisation
- Includes: calls_included, whatsapp_included, sms_included, overage_per_min_pence
- All orgs on same plan get same limits
```

**Used by:**
- Subscription billing cycle (every month org gets fresh allowance)
- Usage wallet tracking (`OrgUsagePeriod`)
- Overage invoicing

---

### B. **Service Pricing Rules** (Survey/Interview per-order pricing)
**Purpose:** Calculate cost of one-off service orders (Survey campaigns, Interview screening).

**Model:** `ServicePricingRule`, `PlatformService`
```
- Service: code (survey, interview), name, description
- Rules: channel (whatsapp, call, ai_call, zoom), rule_type, bundle sizing, overage rates
- Stateless — pricing rule is looked up at quote time, not stored on the order
```

**Used by:**
- `PlatformCatalogService.calculate_quote()` — computes cost when user builds order
- `ServiceOrder` stores `quote_total_pence` and `quote_breakdown_json` (lines + prices)
- Admin can preview quote before order is placed

**Example Quote Calculation (Survey):**
```
Survey 100 recipients:
  - base fee (flat_per_order): £5.00
  - whatsapp bundle (100 @ £15): £15.00
  - ai_call per-person (100 × 18p): £18.00
  Total: £38.00
```

---

### C. **Organisation Usage & Balances** (Subscription entitlements)
**Model:** `Organisation`
```
- survey_credits_balance: int (one-off survey orders? unclear)
- interview_credits_balance: int (one-off interview orders? unclear)
```

**Actual Usage Tracking:** `OrgUsagePeriod` (what's actually metered)
```
- org_id, period_start, period_end, status
- calls_included, calls_used, calls_percent
- whatsapp_included, whatsapp_used
- sms_included, sms_used
- pack_credits_included, pack_credits_used (for service orders?)
- overage_per_min_pence, overage_invoiced_pence
- warned_at_80 (flag if org hits 80% usage)
```

**How it works:**
1. When org signs up / changes plan → `UsageWalletService` creates fresh `OrgUsagePeriod` for the month
2. Each call → `calls_used` increments
3. At period end → if `calls_used > calls_included` → overage is invoiced
4. Next month → new period opens with fresh allowance

**No field for "user-approved overage charges"** — system automatically invoices if overage_per_min_pence > 0.

---

### D. **Service Orders & Credits** (One-off purchases)
**Models:** `ServiceOrder`, `ServiceOrderRecipient`
```
ServiceOrder:
  - org_id, service_code (survey | interview)
  - recipient_count, quote_total_pence
  - status (draft, launched, completed)
  - payment_status (unpaid, approved, paid)
  - payment_method (gocardless, manual_cash, unknown)
  - quote_breakdown_json (pricing lines)

ServiceOrderRecipient:
  - order_id, name, phone, email
  - status (pending, in_progress, completed, failed)
  - result_json (survey response, interview transcript?)
```

**Current Status:**
- User builds order (Survey/Interview)
- System calculates quote from ServicePricingRule
- User uploads CSV of recipients
- Order status = "draft" until user "launches"
- Payment is marked separately (manual approval needed or GoCardless)
- **Credits are NOT currently deducted** — service orders are cash orders (BYOP pattern, not subscription-bundled)

---

### E. **Overage / Pay-as-You-Go** (Call overage only)
**Current Implementation:**
- `OrgUsagePeriod.overage_per_min_pence` — set per plan/promo
- If calls used > calls included → invoice overage automatically at period end
- `UsageWalletService.maybe_invoice_overage()` creates internal invoice with provider="internal_overage"

**What's Missing:**
- ❌ No consent flag to opt-in to overage billing
- ❌ No way to disable overage billing (org cannot say "block calls if I hit my limit")
- ❌ No per-service-order overage approval (e.g. survey orders don't have overage concept yet)

---

## 3. CAN SURVEY BUNDLES BE CONTROLLED FROM ADMIN?

### Current State
**Partially. Here's what's controllable:**

#### ✅ YES — Service-wide pricing rules
- Admin can edit Survey pricing rules via `/billing/services-pricing`
- Can set WhatsApp bundle size + price
- Can set AI-call per-person rate
- Can set different rates per channel (whatsapp vs call)
- **But:** pricing is global, not per organisation or tier

#### ❌ NO — Subscription-tier specific bundles
- **Problem:** Subscription plans (Starter, Practice, Group) define monthly call/WhatsApp allowances
- Service orders (Survey, Interview) use global ServicePricingRule, NOT tied to subscription tier
- Admin cannot say "Group plan includes 5 free surveys per month"
- Admin cannot say "Practice plan gets discounted WhatsApp @ £10 instead of £15 per 100"

#### ❌ NO — Per-organisation bundle overrides
- No way to grant org_id a custom survey bundle (e.g. "give Acme Corp 2 free surveys")
- Promo system exists but limited to discount % or flat credits, not bundles

#### ❌ NO — Conditional bundle pricing
- No way to say "Survey WhatsApp is free for Group plan subscribers, £15 for others"
- Pricing is evaluated at quote time with no context of org's subscription tier

### What IS in place for surveys:
1. **Service pricing rules editable in admin** → ✅
2. **Quote calculation before purchase** → ✅
3. **Pricing preview for users** → ❌ (dashboard doesn't fetch pricing yet)
4. **Separate WhatsApp vs AI-call pricing** → ✅ (global)
5. **Bundle pricing (e.g. 100-pack deals)** → ✅
6. **Overage pricing if user goes over bundle** → ✅ (in model, not tested)

**File Paths:**
- Rules: `voxbulk-api/app/models/platform_service.py`
- Quote calc: `voxbulk-api/app/services/platform_catalog_service.py`
- Admin UI: `admin.voxbulk.com/adim-web/src/pages/ServicesPricing.jsx`

---

## 4. CAN DASHBOARD READ PRICING DYNAMICALLY FROM BACKEND?

### Current State: **MOSTLY NO**
Surveys page does NOT exist yet. Billing page loads plans but NOT service pricing.

#### ✅ Subscription Plans (Billing page)
- Dashboard calls `GET /billing/plans`
- Loads Starter, Practice, Group card metadata
- Displays price, features
- All dynamic ✅

#### ❌ Survey/Service Pricing
- **Dashboard has NO Survey or Packages page**
- No frontend to show survey bundles, pricing options, or pay-as-you-go rates
- Service pricing rules exist in backend but unused by frontend

#### ✅ Hardcoded Placeholder (Service Orders)
- `serviceOrdersBridge.js` has hardcoded channel list (WhatsApp, AI call, Zoom, etc.)
- Calls `POST /billing/payment-options` to check if GC or cash available
- Quote preview works (admin can see estimated cost)
- **But:** no user-facing UI to actually place orders (admin can approve, but user can't self-serve)

### What Dashboard Currently Fetches
| Endpoint | Data | Used By | Dynamic? |
|----------|------|---------|----------|
| `GET /billing/plans` | Subscription plans (name, price, features) | Billing page, Signup | ✅ |
| `GET /billing/subscription` | Current org plan, period, renewal | Billing KPI | ✅ |
| `GET /billing/usage-summary` | Call/WhatsApp usage, overage | Billing KPI | ✅ |
| `GET /billing/payment-options` | Can pay with GoCardless? Cash? | Billing page | ✅ |
| `POST /billing/platform-services/quote-preview` | Quote for hypothetical order | Admin only | ✅ |

### What's Missing for Survey Phase 1
- ❌ `GET /billing/survey-bundles` (or equivalent) — fetch available survey options + pricing
- ❌ Dashboard page to display survey packages (equivalent to billing cards)
- ❌ Survey order builder UI calling `/platform-services/quote-preview`
- ❌ Integration of `ServiceOrder` creation into dashboard

**File Paths:**
- Dashboard fetch logic: `dashboard.voxbulk.com/dashboard-web/src/billingBridge.js`
- Service order admin: `dashboard.voxbulk.com/dashboard-web/src/serviceOrdersBridge.js` (incomplete)

---

## 5. CREDITS AND BALANCES

### Balances on Organisation

#### A. **Hard Balances** (tracked per subscription plan)
```
OrgUsagePeriod (created fresh each month):
  - calls_included: int (from plan)
  - calls_used: int (incremented per call)
  - whatsapp_included: int (from plan)
  - whatsapp_used: int (incremented per WhatsApp)
  - sms_included: int (from plan)
  - sms_used: int (incremented per SMS)
  - pack_credits_included: int (from plan? unclear)
  - pack_credits_used: int (?)
```

#### B. **Survey/Interview Credits** (unclear, not actively used)
```
Organisation model:
  - survey_credits_balance: int
  - interview_credits_balance: int
```
**Status:** These fields exist but NO service deducts from them. Service orders are pay-per-order (cash), not subscription-bundled.

#### C. **Promo Credits**
- `PromoOffer` can grant flat credit bonus (e.g. "free £50")
- Applied to organisation, consumed at checkout
- Not yet tied to surveys

### How Are Credits Granted?

1. **Plan allowance** — when org subscribes to plan, `OrgUsagePeriod` is created with `calls_included` from plan
2. **Promo offer** — admin creates promo with discount or fixed credit (e.g. "£50 off first month")
3. **Manual admin action** — (not yet implemented in UI) change `survey_credits_balance` directly
4. **Service order payment** — org pays invoice (cash or GoCardless), order is marked paid

### How Are Credits Consumed?

1. **Calls** — each call increments `calls_used`, checked against `calls_included` in usage query
2. **WhatsApp** — each message increments `whatsapp_used`
3. **SMS** — each message increments `sms_used`
4. **Survey orders** — quoted at order time, paid separately (no credits deducted yet, order moves to "approved" after payment)
5. **Overage** — if usage exceeds included, invoice is created (not "pay-as-you-go" in the sense of accumulated balance, but billed at month end)

**File Paths:**
- Usage tracking: `voxbulk-api/app/services/usage_wallet_service.py`
- Balance queries: `voxbulk-api/app/routers/billing.py` (GET `/billing/usage-summary`)

---

## 6. OVERAGE / PAY-AS-YOU-GO SUPPORT

### Current State: **PARTIAL**

#### ✅ What Exists (for Calls)
- **Field:** `Plan.overage_per_min_pence`, `OrgUsagePeriod.overage_per_min_pence`
- **Mechanism:** If `calls_used > calls_included`, auto-calculate overage cost
- **Invoice:** At period end, `UsageWalletService.maybe_invoice_overage()` creates internal invoice
- **Email:** Invoice is emailed to org contact
- **Tested:** Yes, there are tests for overage invoicing

#### ❌ What's Missing

**1. User Consent/Opt-in**
- No field on `Organisation`, `Plan`, or `Subscription` to capture "user agrees to overage charges"
- No checkbox in admin like "Allow automatic overage invoicing"
- No dashboard toggle like "If I run out of calls, charge me automatically"

**2. Hard Limit / Soft Limit Options**
- No way to set "block calls if limit reached" (soft limit = overage, hard limit = deny)
- System always overages if overage_per_min_pence > 0

**3. Per-Service-Order Overage** (for Surveys)
- Service orders have `quote_total_pence` but no `overage_unit_price_pence`
- No way to say "if survey goes over 100 contacts, charge 15p per extra contact"
- ServicePricingRule has `overage_unit_price_pence` field but not used in quote calculation

**4. Overage Approval/Notification**
- Overage is invoiced automatically
- No pre-invoice warning/approval step
- No "notify org before charging" option

**5. Accumulating Credit Balance**
- "Pay-as-you-go" typically means org can prepay £100 credit, consume it slowly
- Current system is "invoice after usage" (pay-per-month), not prepaid credit pool

### Design for Overage Consent

**To support your requirement:** "If package finishes, I agree to pay pay-as-you-go charges"

**What's needed:**
1. Add field to `Organisation` or `Subscription`:
   ```python
   allow_overage_charges: bool = False
   overage_consent_accepted_at: datetime | None = None
   ```

2. Add field to `OrgUsagePeriod`:
   ```python
   overage_consent_acknowledged: bool = False
   ```

3. Add dashboard checkbox (Settings / Billing):
   - "Automatically charge for overage usage beyond my plan"
   - If checked → org.allow_overage_charges = True
   - Store acceptance timestamp

4. Modify `UsageWalletService.maybe_invoice_overage()`:
   ```python
   if not org.allow_overage_charges:
       return None  # Don't invoice, just flag as blocked
   ```

5. Add flag to `OrgUsagePeriod`:
   ```python
   overage_blocked_due_to_no_consent: bool = False
   ```

**File Paths:**
- Usage service: `voxbulk-api/app/services/usage_wallet_service.py` (lines 296–372)
- Plan model: `voxbulk-api/app/models/plan.py`
- Org model: `voxbulk-api/app/models/organisation.py`

---

## 7. INTEGRATION CHECKLIST FOR SURVEY PHASE 1

### What Already Works
- ✅ Admin can set Survey service pricing rules (WhatsApp bundle, AI-call per-person)
- ✅ Admin can preview quote calculations
- ✅ Backend can calculate quote for any recipient count + delivery method
- ✅ Service orders can be created/launched/completed
- ✅ Payment approval workflow exists (manual or auto via GoCardless)

### What Needs to Be Built

**Backend:**
- [ ] API endpoint `GET /billing/survey-offerings` (or reuse platform-services)
  - Return available survey configurations (WhatsApp, AI-call, mixed, etc.)
  - Include pricing rules + bundles
- [ ] Add consent fields to `Organisation` + `Subscription` models
- [ ] Dashboard endpoint `GET /user/settings/overage-consent` / `PUT` to toggle

**Dashboard Frontend:**
- [ ] New **Surveys** page / section
  - Display available survey bundles (pricing, channels, bundle sizes)
  - Load pricing dynamically from backend (`/billing/survey-offerings`)
  - Show current org's balance (if subscription-bundled surveys exist)
  - Build survey order UI
- [ ] **Settings / Billing** section
  - Checkbox: "Allow automatic overage / pay-as-you-go charges"
  - Store consent timestamp

**Admin Frontend:**
- [ ] Ability to view which orgs have overage consent enabled
- [ ] Ability to override/reset consent

### Questions for Requirements

1. **Should surveys be subscription-bundled or always pay-per-order?**
   - Option A: "Group plan includes 5 free surveys/month, Practice has 2, Starter has 0 (pay-per-order)"
   - Option B: "All surveys are pay-per-order regardless of plan tier"
   - Option C: Promo system grants free surveys to specific orgs

2. **Should overage have approval before charging?**
   - Option A: Auto-invoice at month end (current)
   - Option B: Warn org first, require opt-in
   - Option C: Require admin approval for each overage invoice

3. **Should WhatsApp/AI-call pricing differ by subscription tier?**
   - E.g. "Group plan members get WhatsApp @ £10/100, Practice @ £15/100"
   - Or always global pricing with tier-based discounts?

4. **For survey credits on `Organisation` model:**
   - Are these intended for "free surveys granted to org"?
   - Or remove and rely only on pay-per-order?

---

## Summary Table

| Component | Status | Notes |
|-----------|--------|-------|
| **Admin — Subscription Plans** | ✅ Fully built | Create, edit, activate, pricing, features |
| **Admin — Service Pricing Rules** | ✅ Fully built | Survey/Interview bundles, channels, overage rates |
| **Admin — Promo Offers** | ✅ Exists | Discounts, free credit, overage rate override |
| **Dashboard — Billing Page** | ✅ Fully built | Loads plans dynamically, shows usage |
| **Dashboard — Survey Page** | ❌ Missing | No UI to browse/order surveys (product roadmap; not security Phase 1–10) |
| **Dashboard — Settings** | ⚠️ Partial | Overage consent wired in remediation PR #10 (Phase 3) — merge/deploy to clear this row |
| **Overage Consent** | ⚠️ Remediation open | PR #10 — `allow_overage` gate + consent timestamp (was ❌ in May 2026 product audit) |
| **Pay-as-you-go (Surveys)** | ✅ Exists in product | Wallet / PAYG launch holds — see billing services (this May table was stale) |
| **Subscription-bundled Surveys** | ⚠️ Partial | Allowance + overage paths exist; marketing “bundled surveys” UX still incomplete |
| **Tier-specific Survey Pricing** | ⚠️ Partial | Per-currency `plan_prices` / org currency; not every tier has unique survey SKUs |

---

**End of product/package audit (2026-05-24)**

---

# Code Audit Findings & remediation (2026-07)

Security / reliability findings from the Cursor code audit, tracked through phased PRs on `menasimuk-hub/Vox-new`. Product sections above (§1–7) remain the May 2026 **pricing/infra** snapshot; this section is the **security remediation** ledger.

## Finding tables

### Critical

| ID | Finding | Remediation |
|----|---------|-------------|
| C1 | Stripe/Airwallex webhook retries can double-credit wallet | Phase 1 — PR #8 (`cursor/billing-webhook-idempotency-bd1f`) |
| C2 | Campaign settlement can double-invoice / double-charge on retry | Phase 2 — PR #9 (`cursor/settlement-idempotency-bd1f`) |

### Medium

| ID | Finding | Remediation |
|----|---------|-------------|
| M1 | `get_order` usable without org scope (tenant IDOR risk) | Phase 7 — PR #14 |
| M2 | Org header fallback when JWT lacks `org_id` | Phase 4 — PR #11 |
| M3 | Celery task status readable cross-org | Phase 7 — PR #14 |
| M4 | Public feedback session mutations by `session_id` alone | Phase 9 — PR #16 |
| M5 | Partner screening owner falls back to any `User` | Phase 7 — PR #14 |
| M6 | Webhook handlers process duplicates (Stripe/AW/Meta) | Phases 1 + 5 — PRs #8, #12 |
| M7 | `ALLOW_INSECURE_WEBHOOKS` in production | Phase 0/1 security — PR #7 (+ Phase 4 `.env.example`) |
| M8 | Telnyx messages trust client org header | Phase 5 — PR #12 |
| M9 | Media stream WS under-authenticated | Phase 5 — PR #12 |
| M10 | Promo redeem race (no unique org+promo) | Phase 8 — PR #15 |
| M11 | Launch/complete charge race | Phase 8 — PR #15 |
| M12 | Overage charged without consent | Phase 3 — PR #10 |
| M13 | Prod JWT/encryption `change-me` fail-open | Phase 4 — PR #11 |
| M14 | Recipient upload unbounded | Phase 6 — PR #13 |
| M15 | Invite/OAuth missing rate limits | Phase 6 — PR #13 |
| M16 | Deploy leaves `.env` world-readable / sources full file | Phase 9 — PR #16 |
| M17 | Airwallex amounts via `float×100` | Phase 8 — PR #15 |

### Low / info

| ID | Finding | Remediation |
|----|---------|-------------|
| L1 | Root `get_api_key.py` prints secrets | Phase 9 — PR #16 |
| L2 | Booking token in application logs | Phase 9 — PR #16 |
| L3 | OAuth redirect fragment / one-time code UX | **Deferred** — needs frontend + provider console coordination |
| L4 | VAT rates as floats / basis-point cleanup | **Deferred** — dedicated billing PR |
| L5 | Retired `maybe_invoice_overage` leftover risk | Covered with Phase 2 settlement idempotency |
| I5 | Stale naming in this document (§6–7 / summary) | Phase 10 — summary table notes refreshed above |
| I6 | Dependency CVEs not inventoried | Phase 10 — [`docs/security/dependency-audit-2026-07-29.md`](docs/security/dependency-audit-2026-07-29.md) |

## Phase → PR map

| Phase | Branch | PR | Closes |
|-------|--------|----|--------|
| 0 / security baseline | `cursor/security-phase1-audit-bd1f` | #7 | Demo bootstrap, health token, prod insecure-webhook refuse |
| 1 | `cursor/billing-webhook-idempotency-bd1f` | #8 | C1, M6 Stripe/AW |
| 2 | `cursor/settlement-idempotency-bd1f` | #9 | C2, L5 |
| 3 | `cursor/billing-overage-consent-gate-bd1f` | #10 | M12 |
| 4 | `cursor/auth-fail-closed-bd1f` | #11 | M13, M2 |
| 5 | `cursor/webhook-stream-hardening-bd1f` | #12 | M8, M9, M6 Meta |
| 6 | `cursor/upload-rate-limits-bd1f` | #13 | M14, M15 |
| 7 | `cursor/tenant-hygiene-bd1f` | #14 | M1, M3, M5 |
| 8 | `cursor/promo-launch-money-bd1f` | #15 | M10, M17, M11 |
| 9 | `cursor/security-hygiene-bd1f` | #16 | L1, L2, M16, M4 |
| 10 | `cursor/ops-audits-bd1f` | (this) | I5, I6, secret checklist; L3/L4 documented deferred |

**Note:** Several Alembic revisions claim `0208_*` off `0207` across open PRs — rebase/merge heads when landing the stack.

## Explicitly deferred (do not invent scope)

| Item | Why |
|------|-----|
| SQLAlchemy global tenant `with_loader_criteria` middleware | Large rewrite; Phase 7 covers highest-risk call sites |
| Live nginx rate limits / Redis bind | Needs VPS operator access |
| L3 OAuth fragment redesign | UX + frontend + IdP console |
| L4 VAT integer / basis points | Billing correctness PR |
| Git history purge for leaked example secrets | Ops decision after confirming whether live secrets ever matched examples |

## Secret remediation checklist (ops — VPS)

Rotate **on the production VPS** if any live value ever matched historical `.env.example` placeholders or shared demos. This is **not** done by deploy scripts.

- [ ] Confirm `ENV=production` / `prod` and `ALLOW_INSECURE_WEBHOOKS` unset/false
- [ ] Rotate `JWT_SECRET_KEY` if it was ever `change-me` (logs out all sessions)
- [ ] Rotate `ENCRYPTION_KEY` only with a planned re-encrypt path — **do not** swap Fernet keys blindly (breaks stored integration ciphertext)
- [ ] Rotate webhook secrets: Telnyx, Meta, Stripe, Airwallex, GoCardless, Vapi (`VAPI_WEBHOOK_SECRET`, etc.) and update provider consoles
- [ ] Confirm `HEALTH_SECRET_TOKEN` set; `/health/build|db|pricing` return 403 without token
- [ ] Confirm `voxbulk-api/.env` mode `600` after deploy (Phase 9)
- [ ] Admin → Integrations: re-save Telnyx/Meta/Stripe/Airwallex after any key rotation
- [ ] OAuth provider consoles: Google/Apple/LinkedIn redirect URIs still `https://api.voxbulk.com/auth/oauth/{provider}/callback`
- [ ] Optional: `git filter-repo` / history scrub only after confirming secrets were committed (prefer rotation over rewrite)

## Dependency audit (I6)

See [`docs/security/dependency-audit-2026-07-29.md`](docs/security/dependency-audit-2026-07-29.md).

Highlights (2026-07-29 scan):

- Python: 22 advisories in 6 packages (`python-jose`, `cryptography`, `starlette`, `weasyprint`, `ecdsa`, `pytest`)
- npm: dashboard 8 / admin 13 / public 23 total vulns (mix of Vite, ws, Telnyx webrtc → uuid)

Follow-up: dedicated upgrade PRs with build + pytest/vitest — **not** silent majors in Phase 10.

## L3 / L4 (documented only)

**L3 — OAuth fragment / one-time code:** current OAuth callback may expose tokens in ways that deserve a one-time exchange code + frontend handoff. Requires dashboard/public auth UX and provider testing — schedule separately.

**L4 — VAT basis points:** store/compare VAT as integer minor units or basis points end-to-end; avoid float money in VAT math. Touch `country_vat_service` / invoice totals in a billing-focused PR.

---

**End of Code Audit Findings ledger**
