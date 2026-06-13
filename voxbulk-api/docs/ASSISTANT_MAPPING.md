# VoxBulk Assistant — Intent to Endpoint Mapping

Grounded assistant routes live under `/assistant` (customer) and `/admin/assistant` (admin).
Legacy path `/dashboard/help/chat` delegates to the same orchestrator.

## Customer intents

| Intent | Trigger examples | Data sources (in-process) | Highlight | Next actions |
|--------|------------------|---------------------------|-----------|--------------|
| `wallet_low` | "Why is my wallet low?" | `WalletService`, `InvoiceService`, `ServiceOrderService` | `invoice` or `service_order` or `wallet_transaction` | `/account/billing`, `/account/usage` |
| `billing_overview` | "billing", "invoice", "subscription" | `BillingAccessService`, `BillingService`, invoices | `invoice` if outstanding | `/account/billing` |
| `usage_summary` | "usage", "quota", "remaining" | `UsageWalletService`, `BillingMonitorService` | `usage` | `/account/usage` |
| `launch_check` | "Can I launch?" | `BillingAccessService`, `SurveyLaunchEligibilityService` | `service_order` | `/surveys/new?order_id=` |
| `survey_results` | "survey results", "NPS" | `build_survey_results_payload` | `survey_result` | `/surveys/results` |
| `interview_results` | "interview results" | recipients on order | `interview_result` | `/interviews/results/{id}` |
| `feedback_overview` | "feedback", "QR location" | `FeedbackLocationService`, `FeedbackResultsService` | `feedback_location` | `/feedback/results` |
| `create_ticket` | "problem", "issue" | — (pending) | — | confirm → `POST /support/tickets` |
| `create_survey` | "create survey" | — | — | `/surveys/new` |
| `create_template` | "create custom template", "whatsapp template" | — | `service_order` | `/surveys/new?channel=whatsapp` |
| `create_feedback` | "create feedback location" | — | — | `/feedback/new` |
| `product_compare` | "survey vs feedback" | — | — | clarification only |
| `list_surveys` | "my surveys" | `ServiceOrderService.list_orders(survey)` | `service_order` | `/surveys` |
| `list_interviews` | "my interviews" | `ServiceOrderService.list_orders(interview)` | `service_order` | `/interviews` |

## Customer mutations (confirm required)

| Action | Confirm endpoint | Backend execution |
|--------|------------------|-------------------|
| `create_support_ticket` | `POST /assistant/confirm` | `SupportTicketService.create_ticket` |

## Admin intents

| Intent | Requires | Notes |
|--------|----------|-------|
| `admin_*` | `context.organisation_id` | Same handlers as customer, scoped to org |
| Admin mutations | — | Not enabled (`501`) |

## Allowlists

- Customer read: billing, usage, orders, results, feedback, tickets
- Customer mutate: `create_support_ticket` only
- Admin read: support KPIs, invoices, subscriptions (handlers TBD for dedicated admin paths)
- Admin mutate: none in v1

## Structured response fields

All chat responses return `AssistantChatOut`:

- `primary_message`
- `highlight_type`, `highlight_id`, `highlight_label`
- `next_actions[]` (`navigate` | `confirm` | `open_panel`)
- `blocking_reason`
- `confidence`
- `pending_action` (when confirmation needed)

## Frontend

- Chat UI: `LiveChatFab` in `dashboard-web/src/components/top-bar.tsx`
- Highlight context: `dashboard-web/src/lib/assistant-highlight.tsx`
- Row targeting: `data-assistant-highlight="{id}"` on billing, surveys, tickets tables
