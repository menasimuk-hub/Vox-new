# Customer Feedback service

## Audit summary (vox-connect-suite-main vs voxbulk.com)

| Area | vox-connect-suite-main | voxbulk.com (before) | voxbulk.com (after) |
|------|------------------------|----------------------|---------------------|
| Backend / DB | None (UI prototype) | None | `feedback_*` tables, APIs |
| Admin UI | None | None | `/customer-feedback/*` admin pages |
| Dashboard UI | `/feedback/*` mock | None | `/feedback/*` wired to API |
| Industries / types | Hardcoded in wizard | WA Survey only (separate) | `feedback_industries`, `feedback_survey_types` |
| Billing | Shared mock GBP | Single org subscription | Parallel `service_code=customer_feedback`, GC-only |
| WhatsApp | Client QR + wa.me | Survey order flow only | Trigger router on inbound |
| Results | Reuses survey results | N/A | Per-location filters |

Design reference: `vox-connect-suite-main/src/routes/_app.feedback.*.tsx` — layout copied into dashboard-web.

## GoCardless notes

- Feedback subscriptions use Direct Debit only (no wallet top-up, no overage).
- Plans are grouped by market zone (`gb`, `us`, `ca`, `au`) with `PlanPrice` multi-currency rows.
- Enable non-UK packages only after your GoCardless merchant account supports the target scheme/currency.

## Invoice stream

Feedback subscription invoices use prefix `CF-` and `billing_invoices.service_code = customer_feedback`.

## QR trigger format

```
Hello, I want to share feedback for {company} at {branch}. Ref: ACME-MARYLEBONE-A3F2
```

- Plain text only (no emojis) so WhatsApp pre-fill displays reliably on all phones.
- `Ref` code is derived from company + branch name plus a short unique suffix.
- Inbound handler resolves the ref token → location → survey flow.
- Legacy messages with `[ref:token]` still work.

## Workflow (QR → results)

```
QR scan → visitor sends trigger → charge 1 unit (per inbound) → selected topics (1–6)
→ optional open question → optional marketing opt-in → thank-you → English results in dashboard
```

- QR codes use **Admin → Integrations → Telnyx → WhatsApp From** (same number as survey/interview WhatsApp).
- On seed/API boot, that number is copied into `feedback_wa_senders` for QR generation.
- Admin sync: `POST /admin/customer-feedback/wa-senders/sync-from-telnyx`
- **Survey language** — detected from visitor phone country code (English templates for now).
- **Results** — stored with `answer_text_en` for dashboard display.
- **Billing** — 1 WA unit per inbound QR trigger (not per completed survey).

## Package tiers (seed)

| Plan | Locations | Triggers/mo |
|------|-----------|-------------|
| Starter | 1 | 1,000 |
| Pro | 5 | 3,000 |
| Business | 20 | 10,000 |

Promo sends (future) deduct from org **promo wallet** at `promo_message_cost_minor` per message.

## Admin UI

| Route | Purpose |
|-------|---------|
| `/customer-feedback/industries` | Industry list + import English templates |
| `/customer-feedback/industries/:id` | Industry edit + survey types |
| `/customer-feedback/survey-types/:id` | Topic template editor |
| `/customer-feedback/packages` | Multi-currency plan pricing |

## Post-deploy (VPS)

1. Migration **`0119_customer_feedback_workflow`** (`alembic upgrade head`).
2. Admin → Industries → **Import English templates** (140 topic templates + system templates).
3. Optional: per-industry **Sync to Telnyx** (marks templates `submitted` until real Telnyx push is wired).

## Known gaps (not yet shipped)

| Gap | Notes |
|-----|--------|
| Telnyx Meta template push | Templates stored as draft; sync sets `submitted` only |
| Promo wallet top-up | Models exist; no Stripe/Airwallex top-up or send UI |
| 50-language templates | English MD import only (Track K) |
| Dashboard step 3 QR | Local preview QR; step 4 uses API preview with real trigger |
| Hub vs dedicated routes | Subscriptions/locations/results still on `CustomerFeedbackHub` tabs |
| GoCardless non-GB | Enable EU/US/CAD/AUD only when GC merchant supports scheme |
