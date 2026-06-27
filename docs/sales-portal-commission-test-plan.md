# Sales portal + commission — test plan

Covers the salesman experience inside the user dashboard and the commission-on-payment
billing hook.

- **Feature:** Sales menu in the user dashboard (`/sales`, `/sales/deals`, `/sales/wallet`)
  and automatic commission accrual when a linked customer pays a subscription invoice.
- **Commit:** `d9df9f4`
- **Backend:** `voxbulk-api/app/services/sales_rep_service.py`,
  `invoice_payment_service.py`, `gocardless_billing_webhook_service.py`
- **Frontend:** `dashboard.voxbulk.com/dashboard-web/src/routes/_app.sales.*`,
  `components/app-sidebar.tsx`, `lib/guards/settings-route.ts`

## Prerequisites

- A test salesman account (Admin → Salesmen → Create salesman). Note its **promo code**.
- A normal org owner/manager account for the negative test.
- Telnyx configured (only for the optional WA/call/offer sends).

## Commission rule (expected behaviour)

| Plan interval | When commission accrues | Amount |
|---------------|-------------------------|--------|
| Monthly       | On the **2nd** paid subscription invoice for the org | Full 2nd invoice amount |
| Yearly        | On the **1st** paid subscription invoice | Invoice ÷ 12 |

- At most **one** subscription commission per (salesman, org) — idempotent.
- Accrual is best-effort: it must never block or fail a payment.
- New commissions start as **pending** (no payout action yet).

## Test cases

### 1. Salesman login & sidebar
1. Log in to the dashboard as the salesman.
2. Expect to land on `/sales`.
3. Sidebar shows **Sales** group: My customers, Won deals, Wallet & commission — plus **Profile settings**.
4. No interviews / surveys / feedback / billing menus.

- [ ] Pass

### 2. My customers (`/sales`)
1. Add a customer → **Save customer**.
2. Customer appears in the Visited customers table.
3. **Edit** a row → form fills at top; update saves.
4. **Delete** a row → row disappears after confirm.
5. (Optional, Telnyx) Send WA survey / AI call / offer (WA + email) / Show QR.

- [ ] Pass

### 3. Won deals (`/sales/deals`)
1. With no conversions: empty state shown.
2. After a customer signs up with the promo code: deal shows **Converted**.

- [ ] Pass

### 4. Wallet (`/sales/wallet`)
1. Before any paid customer: revenue and commission are **£0**.
2. After a linked customer pays: figures update (see case 5).

- [ ] Pass

### 5. Billing → commission (core)
1. Sign up a new customer org using the salesman's **promo code** at checkout.
2. Pay the subscription invoice (card / wallet / Direct Debit).
3. Monthly plan: pay the **2nd** invoice → commission accrues.
4. Yearly plan: commission accrues on the **1st** payment (≈ invoice ÷ 12).
5. Salesman **Wallet** → pending commission increases.
6. DB check (optional): a `sales_commissions` row exists for that org + rep.

- [ ] Pass

**If commission stays £0, check:**
- Customer actually used the salesman's promo code at signup.
- Invoice was `kind=subscription` and `status=paid`.
- Monthly: it was the **2nd** paid subscription invoice.

### 6. Non-salesman user
1. Log in as a normal org user.
2. No Sales menu in sidebar.
3. Visiting `/sales` directly redirects away.

- [ ] Pass

### 7. Admin salesmen page
- Create salesman popup, Edit, Reset password, Disable/Enable, Delete.
- Profile modal shows sample data when empty.

- [ ] Pass

## Quick smoke test (5 min)

| Step | Expected |
|------|----------|
| Salesman login | `/sales`, Sales sidebar visible |
| Save 1 customer | Shows in table |
| Normal user login | No Sales menu |
| Customer pays with promo (2nd month if monthly) | Wallet commission > £0 |

## Known gaps (not bugs)

- Attribution relies on the promo code reaching `OrgUsagePeriod.promo_code` (or a
  `SalesCustomer.org_id`). No code entered at signup → no commission.
- No automatic customer → org conversion; linking is by promo code only.
- Commission stays `pending` — no admin payout / mark-paid action yet.
