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

Abuu migrations run via `alembic -c alembic_abuu.ini upgrade head` during deploy (includes `0014_abuu_menu_intelligence`).

If upgrade fails with `Data too long for column 'version_num'` (revision ids longer than VARCHAR(32)):

```bash
cd voxbulk-api && source .venv/bin/activate
mysql -u USER -p sql_abuu -e "ALTER TABLE alembic_version MODIFY version_num VARCHAR(64) NOT NULL;"
alembic -c alembic_abuu.ini upgrade head
```

If `0013` DDL already ran but the version stamp failed, widen the column then bump the row manually before upgrading to `0014`:

```sql
ALTER TABLE alembic_version MODIFY version_num VARCHAR(64) NOT NULL;
UPDATE alembic_version SET version_num='0013_abuu_session_context_mediumtext' WHERE version_num='0012_abuu_gaza_agent_snapshots';
```

## Troubleshooting WhatsApp silence

### Telnyx opt-out (STOP)

If logs show `block rule` for your number, send **`UNSTOP`** or **`START`** to the WhatsApp sender (e.g. `+447822002055`). Telnyx has no API to remove opt-outs — the user must message back.

### Bloated Abuu session (`context_json` too long)

Symptom: inbound logged but no reply; manual test raises `Data too long for column 'context_json'`.

Clear session for a phone:

```bash
cd voxbulk-api && source .venv/bin/activate
python - <<'PY'
from app.core.abuu_database import get_abuu_sessionmaker
from app.abuu.services.order_draft_service import AbuuOrderDraftService
phone = "+447954823445"  # your test number
with get_abuu_sessionmaker()() as db:
    AbuuOrderDraftService.clear_session(db, phone)
    db.commit()
print("cleared", phone)
PY
redis-cli DEL "abuu:session:+447954823445"
```

After deploy with session compaction fix, new sessions stay small automatically.

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

## Menu intelligence (migration 0014)

After deploy, run Abuu migrations if not already at head:

```bash
cd voxbulk-api
alembic -c alembic_abuu.ini upgrade head
```

Apply structured allergen/recipe/dietary tags to pilot menus:

```bash
cd voxbulk-api
python scripts/enrich_abuu_menu_tags.py --pilot-five --apply
python scripts/enrich_abuu_menu_tags.py --audit-unclassified   # read-only report
```

Config (`.env`):

- `ABUU_MENU_INTELLIGENCE_ENABLED=true` — structured search + dietary filtering
- `ABUU_ALLERGEN_STRICT_MODE=true` — exclude items missing dietary confirmation when customer requires vegan/vegetarian/etc.
- `ABUU_PORTAL_TOKEN_EXPIRE_DAYS=30` — restaurant/driver portal JWT lifetime

## Voice interpretation (post-STT)

**Product rule:** Raw STT transcript is only an input signal, not final customer intent. Abuu normalizes and interprets Arabic food-ordering speech against menu vocabulary before deciding how to respond.

Config (`.env`):

- `ABUU_VOICE_INTERPRETATION_ENABLED=true` — normalize + lexicon + menu fuzzy before orchestrator
- `ABUU_VOICE_INTENT_STRONG_THRESHOLD=0.72` — proceed without clarification
- `ABUU_VOICE_INTENT_CLARIFY_THRESHOLD=0.45` — ask one short Arabic clarification below strong
- `ABUU_VOICE_MENU_FUZZY_MIN_SCORE=45` — rapidfuzz threshold (same as agent kb)
- `ABUU_VOICE_DEEPSEEK_RECOVERY_ENABLED=true` — cheap JSON recovery only when lexicon+fuzzy weak
- `ABUU_VOICE_STT_PROVIDER_ORDER=deepinfra,whisper_cpp,groq` — STT chain order (future extension)

After deploy with orchestrator mode, inspect logs for `abuu_voice_interpretation` fields when testing voice notes.

**Live trace (after deploy with `abuu_wa_trace` logging):**

```bash
tail -f /tmp/voxbulk-api.log | grep --line-buffered abuu_wa_trace
```

**Full STT diagnostic on VPS:**

```bash
chmod +x scripts/vps-abuu-voice-stt-check.sh
./scripts/vps-abuu-voice-stt-check.sh
```

**Note:** Customer-stated `allergy_note` on an order is separate from item-level `allergen_tags_json` on menu items. The waiter captures the note at confirm time; tags drive search safety.

Future cities: add rows to `abuu_market_agents` and set `ABUU_MARKET_AGENT`.
