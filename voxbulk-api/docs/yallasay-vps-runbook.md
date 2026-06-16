# YallaSay / Gaza Agent — VPS runbook

Deploy target for the restaurant portal and WhatsApp ordering pilot: **restaurant.yallasay.com** (not abuu.voxbulk.com).

## Recommended `.env` (voxbulk-api)

```env
ABUU_MARKET_AGENT=ps-gaza
ABUU_AGENT_ENABLED=true
ABUU_CONVERSATION_MODE=orchestrator
ABUU_AGENT_WAITER_MODE=false
ABUU_PILOT_ONLY=true
ABUU_IGNORE_DISTANCE=true
ABUU_DEEPSEEK_ENABLED=true
ABUU_AGENT_MODEL=deepseek-chat
VOX_UVICORN_WORKERS=2
```

## Deploy

```bash
cd /www/voxbulk   # or your repo path
git pull origin main
./deploy-vps.sh
```

Abuu migrations run via `alembic -c alembic_abuu.ini upgrade head` during deploy (includes `0012_abuu_gaza_agent_snapshots`).

## Seed five pilot restaurants + menus

```bash
cd voxbulk-api
source .venv/bin/activate
python scripts/seed_yallasay_full_menu.py --pilot-five
```

Rebuild WhatsApp snapshots after seed or menu edits:

```bash
curl -X POST http://127.0.0.1:8000/abuu/food/rebuild \
  -H "X-Abuu-Internal-Key: YOUR_INTERNAL_KEY"
```

Restart API:

```bash
cd .. && ./vox.sh restart
```

## Verify

- Portal login: Sham Chicken (`abuu-rest-chicken`) at https://restaurant.yallasay.com
- Food API (local): `GET /abuu/food/restaurants?lang=ar` — response must **not** contain `[id=`
- WhatsApp: send `yallasay` → warm greet + “what are you craving?” (no restaurant dump, no internal IDs)
- WhatsApp: send `سمك` or `fish` → dish suggestions across pilots (not a restaurant list)
- Cross-restaurant: add item from restaurant A, then try restaurant B → blocked with 15 ₪ fee explanation

`deploy-vps.sh` rebuilds Abuu snapshots after migrate. To force refresh:

```bash
curl -X POST http://127.0.0.1:8000/abuu/food/rebuild \
  -H "X-Abuu-Internal-Key: YOUR_INTERNAL_KEY"
```

## Architecture (short)

```
WhatsApp (text + voice transcript)
  → inbound_service
  → AbuuConversationOrchestrator (when ABUU_CONVERSATION_MODE=orchestrator)
       intent_router → fact_bundle (DB) → action_runner + restaurant_guard → reply_composer → wa_sanitize
  → legacy skill_router for name/address/substitution steps only
  → MySQL abuu_wa_snapshots + /abuu/food/*
```

Future cities: add rows to `abuu_market_agents` and set `ABUU_MARKET_AGENT`.
