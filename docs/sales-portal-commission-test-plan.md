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
1. Admin creates salesman → verify `promo_offers` row exists with `offer_type=sales_wallet_voucher` and `wallet_credit_pence=2000`.
2. Rep sends offer email → verify branded template (logo, tagline, signup link to `voxbulk.com/signin?promo=CODE`).
3. Customer opens signup link → signin page shows offer banner and passes promo on register (or OAuth).
4. After signup: org wallet +£20; `promo_wallet_balance_pence=2000`; campaign launch blocked if only promo credit available.
5. Customer pays subscription → commission accrues on 2nd invoice (monthly) or 1st (yearly).
6. Admin → Salesmen → mark pending commissions paid → salesman Wallet shows paid commission.

- [ ] Pass

### 5b. £20 wallet voucher restrictions
1. Org with only promo wallet credit (£20, no top-up).
2. Survey/interview launch estimate shows shortfall (promo credit excluded).
3. Customer feedback promo campaign invoice paid from wallet → blocked with clear message if only promo credit.

- [ ] Pass

### 5c. Automated pytest
```bash
cd voxbulk-api
pytest tests/test_sales_rep_promo_flow.py tests/test_promo_offer_service.py tests/test_assistant.py -q
python scripts/audit_email_templates.py
```

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

- Attribution via promo code on signup (`OrgUsagePeriod.promo_code`) and auto-link of `SalesCustomer.org_id` when email/mobile matches.
- Admin can mark commissions paid via `POST /admin/sales-reps/{rep_id}/commissions/mark-paid`.
