# VoxBulk Assistant — Intent to Endpoint Mapping (v1.5)

Grounded assistant routes live under `/assistant` (customer) and `/admin/assistant` (admin).
Legacy path `/dashboard/help/chat` delegates to the same orchestrator.

When `ASSISTANT_LLM_ENABLED=true`, customer chat uses `LlmAssistantOrchestrator` (classify + synthesize) with regex fallback. Handler-only intents (navigation, templates, tickets) always delegate to rich handlers in `orchestrator.py`.

## LLM configuration

```env
ASSISTANT_LLM_ENABLED=true
ASSISTANT_LLM_PROVIDER=deepinfra   # openai | deepseek | deepinfra | groq
ASSISTANT_LLM_MODEL=mistralai/Mistral-Small-3.2-24B-Instruct-2506
```

## Read-only model

- **Read:** billing, usage, campaigns, results, feedback, tickets, subscription
- **Navigate only:** explain where to go; offer `ui_commands` / `next_actions`
- **One write exception:** `create_support_ticket` after explicit confirm — ticket body includes full diagnostic context
- **No auto-execute:** launch, pay, delete, template edits, integration changes

## Dashboard catalog

Single source of truth: `app/services/assistant/dashboard_catalog.py` — mirrored from dashboard sidebar routes. Filtered by `context.enabled_services[]` from the frontend.

## Customer intents (data + navigation)

| Intent | Trigger examples | Data tool | Highlight | Primary nav |
|--------|------------------|-----------|-----------|-------------|
| `wallet_low` | "Why is my wallet low?" | `wallet` | invoice / order / wallet | `/account/billing` |
| `billing_overview` | "billing", "invoice" | `billing_access` | invoice | `/account/billing` |
| `billing_subscription` | "my plan", "subscription" | `billing_subscription` | — | `/account/packages` |
| `usage_summary` | "usage", "quota" | `usage_summary` | usage | `/account/usage` |
| `usage_breakdown` | "usage breakdown", "by campaign" | `usage_breakdown` | usage | `/account/usage` |
| `launch_check` | "Can I launch?" | `billing_access` + eligibility | service_order | `/surveys/new` |
| `survey_results` | "survey results", "NPS" | `survey_results` | survey_result | `/surveys/results` |
| `interview_results` | "interview results" | `interview_results` | interview_result | `/interviews/results` |
| `feedback_overview` | "feedback", "QR" | `feedback_locations` | feedback_location | `/feedback/results` |
| `feedback_subscription` | "feedback subscription" | `feedback_subscription` | — | `/account/feedback/packages` |
| `list_surveys` | "my surveys" | `list_service_orders` | service_order | `/surveys` |
| `list_interviews` | "my interviews" | `list_service_orders` | service_order | `/interviews` |
| `list_tickets` | "my support tickets" | `list_tickets` | ticket | `/account/support/tickets` |
| `invoice_detail` | "invoice INV-123" | `invoice_detail` | invoice | `/account/billing` |
| `ticket_detail` | "ticket #123" | `ticket_detail` | ticket | `/account/support/tickets` |
| `campaign_detail` | order UUID in message | `service_order_detail` | service_order | `/surveys` or `/interviews` |

## Customer intents (navigation / coaching only)

| Intent | Route | Notes |
|--------|-------|-------|
| `create_survey` | `/surveys/new` | Wizard guidance |
| `create_interview` | `/interviews/new` | Wizard guidance |
| `create_feedback` | `/feedback/new` | QR location wizard |
| `create_template` | `/surveys/new?channel=whatsapp` | Custom WA template steps |
| `product_compare` | — | Survey vs interview vs feedback |
| `manage_services` | `/settings/services` | Enable/disable sidebar modules |
| `open_settings` | `/settings/profile` | Profile + services |
| `open_packages` | `/account/packages` | Plans and pricing |
| `open_faq` | `/account/support/faq` | Help articles |
| `open_integrations` | `/settings/integrations` | View-only (policy blocks edits) |
| `open_team` | `/settings/team` | Team invites |
| `open_audit` | `/settings/audit` | Audit log |
| `open_opt_out` | `/settings/opt-out` | Do-not-contact list |
| `recovery_overview` | `/recovery` | Recovery modules (service-gated) |
| `followup_overview` | `/follow-up` | WhatsApp reminders (service-gated) |
| `survey_reports` | `/surveys/reports` | Reports vs Results |
| `interview_reports` | `/interviews/reports` | Reports vs Results |
| `general_help` | `/` | Unknown intent — catalog examples + `suggested_prompts` |

## Customer mutations (confirm required)

| Action | Confirm endpoint | Backend execution |
|--------|------------------|-------------------|
| `create_support_ticket` | `POST /assistant/confirm` | `SupportTicketService.create_ticket` (body includes diagnostic JSON) |

Confirm button label in UI: **Send ticket to support**.

## Policy coaching

Blocked requests return `policy_refused=true`, `suggested_prompts[]`, and navigation to the correct screen (e.g. billing tampering → `/account/billing`).

## Admin intents

| Intent | Requires | Notes |
|--------|----------|-------|
| `admin_*` | `context.organisation_id` | Same handlers as customer, scoped to org |
| Admin mutations | — | Not enabled (`501`) |

## Allowlists

- Customer read: `CUSTOMER_READ_TOOLS` in `allowlists.py`
- Customer mutate: `create_support_ticket` only
- Admin read: support KPIs, invoices, subscriptions (handlers TBD for dedicated admin paths)
- Admin mutate: none in v1

## Structured response fields

All chat responses return `AssistantChatOut`:

- `primary_message`
- `highlight_type`, `highlight_id`, `highlight_label`
- `next_actions[]` (`navigate` | `confirm` | `open_panel`)
- `ui_commands[]`
- `suggested_prompts[]` (policy refusals and fallbacks)
- `blocking_reason`
- `confidence`
- `pending_action` (when confirmation needed)
- `policy_refused`, `error_occurred`, `support_report_token`

## Frontend

- Chat UI: `LiveChatFab` in `dashboard-web/src/components/top-bar.tsx`
- Context sent with each message: `current_route`, `enabled_services[]`
- Clickable `suggested_prompts` chips on policy/fallback responses
- Highlight context: `dashboard-web/src/lib/assistant-highlight.tsx`
- Row targeting: `data-assistant-highlight="{id}"` on billing, surveys, tickets tables
