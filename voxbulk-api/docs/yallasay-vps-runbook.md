# YallaSay / Gaza Agent — VPS runbook

Deploy target for the restaurant portal and WhatsApp ordering pilot: **restaurant.yallasay.com** (not abuu.voxbulk.com).

## Recommended `.env` (voxbulk-api)

```env
ABUU_MARKET_AGENT=ps-gaza
ABUU_AGENT_ENABLED=true
ABUU_AGENT_WAITER_MODE=true
ABUU_PILOT_ONLY=true
ABUU_IGNORE_DISTANCE=true
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
- Food API (local): `GET /abuu/food/restaurants`, `GET /abuu/food/restaurants/{id}/menu`
- WhatsApp: send `yallasay` or `abuu` → should list five pilot restaurants by name (not always the same one)

## Architecture (short)

```
WhatsApp → inbound_service → skill_router (lists from snapshots)
         → Gaza Agent (DeepSeek, 1 turn, waiter mode) when open chat
         → MySQL abuu_wa_snapshots + /abuu/food/*
```

Future cities: add rows to `abuu_market_agents` and set `ABUU_MARKET_AGENT`.
