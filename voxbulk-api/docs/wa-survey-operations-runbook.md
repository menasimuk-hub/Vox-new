# WA Survey — operations runbook

Day-2 guide for support and ops. Technical design: [wa-survey-adaptive-engine.md](./wa-survey-adaptive-engine.md).

## Admin surfaces

| Surface | URL (admin dev) | Capability |
|---------|-----------------|------------|
| WA Survey types | `/settings/wa-survey` | Types, templates, picker kill switch |
| Flow editor | `/settings/wa-survey/:typeId/flows` | Validate / publish graph |
| Simulator | `/settings/wa-survey/simulator` | End-to-end flow test (port **5174**) |
| Running surveys | `/operations/running-surveys` | Per-order contacts + **WA sessions** tab |
| WA insights | `/operations/wa-survey-insights` | Platform metrics + session drill-down |

## Pre-launch checklist (per survey type)

1. **Readiness** — open type edit → readiness panel; fix blocking items (templates, published flow).
2. **Publish flow** — graph orders need a **published** default flow for the order privacy mode.
3. **Simulator** — type edit → **Simulate workflow** (or deep link with `survey_type_id` + `auto_start=1`).
4. **Order config** — `survey_channel: whatsapp`, `flow_engine: graph` (or `linear` fallback), frozen `whatsapp_flow` on the order.

## AI picker controls

| Control | Where | Effect |
|---------|-------|--------|
| Env `WA_SURVEY_AI_PICKER_ENABLED` | API host | Global off overrides platform on |
| Platform row `wa_survey_platform_settings` | DB / types page | Platform enable |
| Kill switch | `/settings/wa-survey` | Blocks all picker calls when on |
| Per-order `ai_picker_enabled` | Order `config_json` | Required for graph + picker |
| Max calls | Platform settings | Default 3 per session |

Insights page shows live picker status (`platform_enabled`, `kill_switch`, `max_calls_per_session`).

## Observability APIs

Ops role (`CAP_ORG_OPS`) — proxied under platform services:

```
GET /admin/platform-services/surveys/wa-observability/overview?since_days=7&order_id=
GET /admin/platform-services/surveys/wa-sessions?order_id=&limit=100
GET /admin/platform-services/surveys/wa-sessions/{session_id}
```

Integration role (`CAP_INTEGRATION`) — same data under:

```
GET /admin/wa-survey/observability/overview
GET /admin/wa-survey/sessions
GET /admin/wa-survey/sessions/{session_id}
```

Recipient detail on running surveys includes `wa_survey_session` when a session exists.

### Key metrics (overview)

- `session_count`, `sessions_by_status`, `sessions_by_flow_mode`
- `outcome_counts`, `delivery_failure_count`, `template_send_failure_count`, `text_fallback_count`
- `picker_invocation_count`, `ai_picker_fallback_count`, `top_branch_rule_keys`

### Session detail

- `session` — status, flow_mode, outcome, `outcome_delivery` (normalized schema)
- `answers`, `decisions`, `picker_debug`, `branch_path`

## Inbound safety (P6)

- Duplicate Telnyx webhooks: dedupe by `log_id` / `inbound_message_id` on `wa_conversation` before advancing.
- Outcome delivery stored in `outcome_delivery_json` (see `survey_outcome_delivery_schema.py`).

## Staging → production

1. Run simulator on staging type with production-equivalent privacy mode.
2. Publish flow; confirm readiness green.
3. Smoke one real order with 1–2 internal numbers.
4. Watch **WA Survey insights** for delivery failures and picker fallbacks for 24h.
5. Enable platform picker only after graph paths are validated.

## Troubleshooting

| Symptom | Check |
|---------|--------|
| No WA sessions on order | Order started? `survey_channel` whatsapp? Inbound webhook reaching API? |
| Session stuck `active` | Last inbound time; recipient replied? Telnyx queue |
| Outcome not delivered | Session detail → `outcome_delivery`; template approval / `template_send_failed` |
| Picker always fallback | Kill switch, env flag, `ai_picker_enabled`, graph has `ai_assisted` edges |
| Duplicate answers | P6 guard logs; same `log_id` twice |

## Tests

```bash
pytest tests/test_survey_wa_p6_safety.py tests/test_survey_wa_readiness_p5.py -q
```
