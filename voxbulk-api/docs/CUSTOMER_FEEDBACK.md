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
✨ I want to start the survey for "{company}" — "{branch}" ✍️📋 [ref:{token}]
```

Inbound WhatsApp handler resolves `ref:` token → location → template sequence.
