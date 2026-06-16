# Abuu WhatsApp Waiter Agent — Architecture

## Product rule

Abuu supports food discovery across multiple restaurants, but checkout is always single-restaurant. Each restaurant order costs 15 NIS. If the customer wants items from two restaurants, create two separate orders.

One menu item = one product record + two language layers (ar/en). Classification, pricing, allergens, dietary tags, and availability belong to the shared product record; names and descriptions are localized.

Raw STT transcript is only an input signal, not final customer intent.

## Layers

| Layer | Module | Responsibility |
|-------|--------|----------------|
| A Input | `inbound_service` → STT | Text and voice notes |
| B Normalize | `waiter/normalization.py` | Script/filler cleanup; no semantic overwrite |
| C Interpret | `waiter/interpretation.py` | Protected tokens + category hints |
| D Intent | `waiter/intent_router.py` | food / restaurant / menu / offer / allergy / cart / … |
| E Menu | `waiter/menu_query_builder.py` + `menu_intelligence` | Typed search, allergen filter |
| F Actions | `waiter/action_runner.py` + `restaurant_guard.py` | Deterministic cart and binding |
| G Reply | `waiter/reply_composer.py` + `wa_sanitize.py` | Waiter tone; no internal IDs |

## Feature flags

- `ABUU_CONVERSATION_MODE=legacy` — skill router
- `ABUU_CONVERSATION_MODE=orchestrator` — current production pipeline
- `ABUU_CONVERSATION_MODE=waiter_v2` — new waiter pipeline
- `ABUU_WAITER_V2_ALLOWLIST` — comma-separated E.164 for pilot phones

## Observability

```bash
tail -f /tmp/voxbulk-api.log | grep --line-buffered abuu_waiter_trace
```

Or: `./scripts/vps-abuu-waiter-trace.sh`

## VPS diagnostic

```bash
./scripts/vps-abuu-voice-stt-check.sh
```
