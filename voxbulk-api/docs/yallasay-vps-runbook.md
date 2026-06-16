# YallaSay / Gaza Agent — VPS runbook

Deploy target for the restaurant portal and WhatsApp ordering pilot: **restaurant.yallasay.com** (not abuu.voxbulk.com).

## Recommended `.env` (voxbulk-api) — agent mode (v1 pilot default)

Use **one** `ABUU_CONVERSATION_MODE` line. DeepSeek Agent + Whisper STT handles all text and voice turns.

```env
ABUU_MARKET_AGENT=ps-gaza
ABUU_AGENT_ENABLED=true
ABUU_CONVERSATION_MODE=agent
ABUU_AGENT_WAITER_MODE=false
ABUU_PILOT_ONLY=true
ABUU_IGNORE_DISTANCE=true
ABUU_DEEPSEEK_ENABLED=true
ABUU_AGENT_MODEL=deepseek-chat
SMART_PIPELINE_ENABLED=false
ABUU_VOICE_INTERPRETATION_ENABLED=false
ABUU_WAITER_TRACE_ENABLED=true
VOX_UVICORN_WORKERS=2
```

Verify the **running process**:

```bash
curl -s http://127.0.0.1:8000/health/abuu-runtime | python3 -m json.tool
# expect: conversation_mode=agent, agent_mode=true, smart_pipeline_enabled=false
```

**Live feed (pretty IN → THINK → OUT):**

```bash
chmod +x scripts/vps-abuu-live-trace.sh scripts/vps-abuu-waiter-trace.sh
./scripts/vps-abuu-live-trace.sh
```

Send WhatsApp while the script runs. Expect `ROUTE pipeline=agent` (not `smart`, `waiter_v2`, or `orchestrator`).

| What you see | Meaning |
|--------------|---------|
| `ROUTE pipeline=orchestrator` or `smart` | Wrong mode — set `ABUU_CONVERSATION_MODE=agent` only once; remove duplicate mode lines |
| `OUT forbidden_hit=True` | Old orchestrator reply_composer path — agent mode not active |
| `agent_mode=false` in health | `ABUU_AGENT_ENABLED=false` or mode not `agent`/`deepseek`/`gaza_agent` |

## WhatsApp numbers — Number 1 vs Number 2

Both lines can **receive** inbound WhatsApp. Routing is by the webhook `to` number:

| Line | E.164 | Admin field | WhatsApp use |
|------|-------|-------------|--------------|
| **Number 1** | +447822002055 | `whatsapp_from` | WA **surveys** + customer feedback + AI voice outbound (landline) — **not Abuu** |
| **Number 2** | +447822002099 | `sms_from_2` + `whatsapp_from_2` | **Abuu / YallaSay** ordering only — text + voice |

Abuu inbound runs **only** when `to` matches Number 2 (`is_yallasay_line`). WA messages to Number 1 go to survey/feedback paths only.

### Admin → Integrations → Telnyx (Save, then Apply Telnyx setup on Number 2)

1. **Number 2 (Abuu):** `+447822002099` → `sms_from_2` and `whatsapp_from_2`
2. **Number 1 (surveys):** `+447822002055` → `whatsapp_from`
3. Click **Apply Telnyx setup (Yallasay line)** — assigns **Number 2** to profile `voxbulk-yallasay` + webhook
4. In **Telnyx console → WhatsApp → WABA:** link **Number 2** (+447822002099), webhook → `https://api.voxbulk.com/telnyx/webhooks/messages`
5. Keep **Number 1** (+447822002055) on the survey WABA/profile only; do not attach Number 1 to the Yallasay profile

Verify:

```bash
curl -s http://127.0.0.1:8000/health/abuu-runtime | python3 -m json.tool
# WA to Number 2 (+447822002099) → ROUTE pipeline=agent
# WA to Number 1 (+447822002055) → survey only, no Abuu
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

## OAuth redirects to localhost:5173 after login

Symptom: after Google/Apple/LinkedIn sign-in you land on `http://localhost:5173/signin#access_token=...` instead of `https://voxbulk.com/signin`.

Cause: API OAuth callback uses `PUBLIC_APP_ORIGIN` ([`auth.py`](../app/routers/auth.py)). Default is `http://localhost:5173` when unset on VPS.

**Fix:**

```bash
cd /www/voxbulk
bash scripts/vps-check-auth-env.sh   # shows what is wrong
```

Add to `voxbulk-api/.env`:

```env
ENV=production
PUBLIC_APP_ORIGIN=https://voxbulk.com
DASHBOARD_APP_ORIGIN=https://dashboard.voxbulk.com
CORS_ALLOW_ORIGINS=https://voxbulk.com,https://www.voxbulk.com,https://admin.voxbulk.com,https://dashboard.voxbulk.com
TRUSTED_HOSTS=api.voxbulk.com,localhost,127.0.0.1
```

Then `./vox.sh restart`. OAuth should redirect to `https://voxbulk.com/signin#access_token=...` and the public site sends you to `https://dashboard.voxbulk.com`.

---

## Troubleshooting WhatsApp silence

Run the diagnostic script first:

```bash
cd /www/voxbulk
bash scripts/vps-abuu-diag.sh
bash scripts/vps-abuu-diag.sh --follow   # while sending Yallasay to +447822002099
```

### Simulate Yallasay inbound (no phone needed)

Use this when real WhatsApp shows silence but you need to know whether **routing + Abuu** work independently of Telnyx WABA delivery:

```bash
cd /www/voxbulk
bash scripts/vps-yallasay-e2e-trace.sh
bash scripts/vps-yallasay-e2e-trace.sh --omit-to    # Telnyx omits `to` field
bash scripts/vps-yallasay-e2e-trace.sh --preflight  # config only
bash scripts/vps-yallasay-e2e-trace.sh --from +44YOURPHONE   # real mobile for full outbound test
bash scripts/vps-yallasay-e2e-trace.sh --route-only          # route + Abuu only (default probe number)
bash scripts/vps-yallasay-e2e-trace.sh --follow     # then tail live trace
```

The default probe customer `+447700900123` is **not** a real WhatsApp user — Telnyx returns 40310 `Invalid 'to' address` on outbound. That is expected. With current script versions, **exit 0** still means routing + Abuu work when using the default probe number.

**Expected when routing works (default probe):**

```
PREFLIGHT  yallasay=+447822002099 profile=40019e47-... agent=True deepseek=True git_sha=...
SIMULATE   text='Yallasay' from=+447700900123 ...
ROUTE      yallasay_line=True abuu_handled=True ...
NOTE       Default probe number is not WA-deliverable ...
EXIT 0 — route + Abuu OK (outbound skipped or probe number not WA-deliverable)
```

**Full outbound test** — use your real mobile (must have messaged 099 before, or within 24h window):

```bash
bash scripts/vps-yallasay-e2e-trace.sh --from +44YOURMOBILE
```

| Exit | Meaning |
|------|---------|
| 0 | Routed to Yallasay + Abuu handled (outbound OK, queued, or probe number not deliverable) |
| 1 | Preflight failed (number missing, API down, Abuu disabled) |
| 2 | Not routed to Yallasay or Abuu did not handle |
| 3 | Abuu handled but Telnyx outbound failed with a **real** `--from` number (profile / opt-out) |

**If simulate works but real phone does not** → Telnyx WABA webhook on +447822002099 is not reaching the API (see below).

**If simulate fails with exit 2** → Number 2 / profile config wrong — run Admin → Telnyx → **Apply Telnyx setup**.

**If exit 3 with `--from +44YOURPHONE`** → run Admin → Telnyx → **Apply Telnyx setup** or check Telnyx WABA opt-out.

### Stale API after git pull

Symptom: `git log -1` shows a newer commit than `/health/abuu-runtime` `git_sha`.

```bash
cd /www/voxbulk
echo '{"git_sha":"'$(git rev-parse --short HEAD)'","git_branch":"'$(git rev-parse --abbrev-ref HEAD)'","built_at":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}' > voxbulk-api/build_info.json
./vox.sh restart
curl -s http://127.0.0.1:8000/health/abuu-runtime | python3 -m json.tool | grep git_sha
```

### Wrong Yallasay messaging profile (phone number instead of UUID)

Symptom: diag shows `yallasay_wa_profile_id: +447822002099` or `FAIL: sms_messaging_profile_id_2 is a phone number`.

Telnyx requires a **messaging profile UUID** for outbound WhatsApp — a phone number in that field causes silent send failures.

1. Admin → Integrations → Telnyx
2. Clear **Yallasay messaging profile ID** if it contains `+447822002099`
3. Click **Apply Telnyx setup (Yallasay line)** — creates `voxbulk-yallasay` profile and saves the UUID
4. **Save** Telnyx settings
5. Re-run `bash scripts/vps-abuu-diag.sh` — expect `yallasay_wa_profile_id: 40000000-....`

### No inbound webhooks for Number 2 (+447822002099)

Symptom: you sent WhatsApp to 099 recently but diag shows no `yallasay_inbound_route` or `abuu_wa_trace IN` lines.

1. Telnyx portal → **Messaging → WhatsApp →** your WABA
2. Confirm **+447822002099** is linked to the WABA
3. Set webhook URL to `https://api.voxbulk.com/telnyx/webhooks/messages` (same as Number 1 surveys)
4. Send `Yallasay` to **+447822002099** (not +447822002055)

Symptom: Admin Messages show inbound `received` but To is `—` and Abuu never replies.

Telnyx sometimes omits the `to` field on WhatsApp webhooks. The API infers the destination from `messaging_profile_id` when present (Yallasay profile → Number 2). If profile is also missing, Apply Telnyx setup and ensure WABA webhook is configured.

### Telnyx opt-out (STOP)

If logs show `block rule` for your number, send **`UNSTOP`** or **`START`** to the WhatsApp sender (e.g. **+447822002099** for Abuu). Telnyx has no API to remove opt-outs — the user must message back.

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
WhatsApp (text + voice)
  → inbound_service → Whisper STT (voice)
  → AbuuAgentLoop (when ABUU_CONVERSATION_MODE=agent) — DeepSeek tool loop
  → legacy skill_router for substitution/name/delivery only in non-agent modes
  → AbuuConversationOrchestrator (when ABUU_CONVERSATION_MODE=orchestrator)
  → WaiterPipeline / SmartPipeline (when ABUU_CONVERSATION_MODE=waiter_v2)
  → MySQL abuu_wa_snapshots + /abuu/food/*
```

## SmartPipeline (experimental / v2)

Use **one** conversation mode line when testing v2 (do not duplicate `orchestrator` and `waiter_v2`):

```env
ABUU_AGENT_ENABLED=true
ABUU_CONVERSATION_MODE=waiter_v2
SMART_PIPELINE_ENABLED=true
ABUU_WAITER_TRACE_ENABLED=true
ABUU_DEEPSEEK_ENABLED=true
```

Verify the **running process** (not just `.env` on disk):

```bash
curl -s http://127.0.0.1:8000/health/abuu-runtime | python3 -m json.tool
# smart_pipeline_enabled must be true, conversation_mode waiter_v2
```

**Live feed (pretty IN → SEARCH → THINK → OUT):**

```bash
chmod +x scripts/vps-abuu-live-trace.sh scripts/vps-abuu-waiter-trace.sh
./scripts/vps-abuu-live-trace.sh
# or last 30 lines without follow:
./scripts/vps-abuu-live-trace.sh --history 30
```

Send a WhatsApp message while the script runs. You should see lines like:

```
[12:04:01] WA_IN  phone=+972… text='دجاج'
[12:04:01] ROUTE  phone=+972… pipeline=smart text="دجاج"
[12:04:01] IN     phone=+972… text=دجاج
[12:04:01] SEARCH items=8 cross_restaurant=true
[12:04:02] THINK  branch=llm action=show_menu
[12:04:02] OUT    reply_preview="هاي أحلى الخيارات…"
[12:04:02] WA_OUT to=+972… body='…'
```

### Troubleshooting live trace

| What you see | Meaning |
|--------------|---------|
| Script prints nothing | No WhatsApp hit API yet — send a message while `./scripts/vps-abuu-live-trace.sh` is running |
| No log file | `./vox.sh status` — API may not be running |
| `SKIP reason=not_abuu` | Message did not match start word and no active Abuu session |
| `SKIP reason=duplicate` | Telnyx retried same message id |
| `ROUTE pipeline=waiter_v2` not `smart` | `SMART_PIPELINE_ENABLED` false at runtime — pull latest, restart |
| `ROUTE pipeline=orchestrator` | Wrong mode — set `ABUU_CONVERSATION_MODE=waiter_v2` only once |
| `OUT forbidden_hit=True` | Old empty-search reply path — SmartPipeline not active or search returned 0 items |
| Only `WAITER` lines, no `ROUTE pipeline=smart` | Old layered waiter — enable SmartPipeline |

## Waiter v2 rollout (`ABUU_CONVERSATION_MODE=waiter_v2`)

Pilot on internal phones first:

```env
ABUU_CONVERSATION_MODE=waiter_v2
ABUU_WAITER_V2_ALLOWLIST=+9725XXXXXXXX,+4479XXXXXXXX
ABUU_WAITER_TRACE_ENABLED=true
ABUU_WAITER_DEEPSEEK_TIMEOUT_SECONDS=8
```

Empty `ABUU_WAITER_V2_ALLOWLIST` = all phones use waiter_v2 when mode is set.

**Live waiter trace:**

```bash
chmod +x scripts/vps-abuu-live-trace.sh
./scripts/vps-abuu-live-trace.sh
# legacy alias:
./scripts/vps-abuu-waiter-trace.sh
```

Rollback to v1 agent: set `ABUU_CONVERSATION_MODE=agent`, `SMART_PIPELINE_ENABLED=false`, and `./vox.sh restart`.
Rollback to orchestrator: set `ABUU_CONVERSATION_MODE=orchestrator` and `./vox.sh restart`.

See also `docs/ABUU_WAITER_ARCHITECTURE.md`.

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

## Voice notes (agent mode)

Send voice to **+447822002099** only (not the survey number **055**).

STT chain (default): **DeepInfra Whisper** → whisper_cpp (local, usually absent) → Groq. No provider change needed if DeepInfra is configured in Admin → Integrations.

Recommended for v1 agent:

```env
ABUU_VOICE_INTERPRETATION_ENABLED=false
```

Diagnose on VPS:

```bash
./scripts/vps-abuu-voice-stt-check.sh
./scripts/vps-abuu-live-trace.sh
# Send Arabic voice note to +447822002099 while tracing
```

| Log line | Fix |
|----------|-----|
| `abuu_stt_all_providers_failed ... failures=deepinfra:not_configured` | Set DeepInfra API key in Admin → Integrations |
| `abuu_stt_all_providers_failed ... failures=deepinfra:empty,groq:...` | Check audio download; verify Groq key as backup |
| No `abuu_wa_trace IN type=voice` | Wrong number or webhook not hitting API |
| `abuu_wa_reply_failed` | Yallasay line not set to 099 or messaging profile missing |
| `ROUTE pipeline=agent` + STT ok but no reply | DeepSeek key in Admin → Integrations |

## Voice interpretation (post-STT — orchestrator / v2 only)

**Product rule:** Raw STT transcript is only an input signal, not final customer intent. Abuu normalizes and interprets Arabic food-ordering speech against menu vocabulary before deciding how to respond.

Config (`.env`):

- `ABUU_VOICE_INTERPRETATION_ENABLED=true` — normalize + lexicon + menu fuzzy before orchestrator
- `ABUU_VOICE_INTENT_STRONG_THRESHOLD=0.72` — proceed without clarification
- `ABUU_VOICE_INTENT_CLARIFY_THRESHOLD=0.45` — ask one short Arabic clarification below strong
- `ABUU_VOICE_MENU_FUZZY_MIN_SCORE=45` — rapidfuzz threshold (same as agent kb)
- `ABUU_VOICE_DEEPSEEK_RECOVERY_ENABLED=true` — cheap JSON recovery only when lexicon+fuzzy weak
- `ABUU_VOICE_STT_PROVIDER_ORDER=deepinfra,whisper_cpp,groq` — STT chain order (future extension)

After deploy with orchestrator mode, inspect logs for `abuu_voice_interpretation` fields when testing voice notes.

**Live trace (end-to-end: STT → agent → reply):**

```bash
chmod +x scripts/vps-abuu-live-trace.sh
./scripts/vps-abuu-live-trace.sh
```

Or raw grep (broader):

```bash
tail -f /tmp/voxbulk-api.log | grep --line-buffered -E 'abuu_agent_trace|abuu_wa_trace|abuu_stt_'
```

`abuu_agent_trace` is always-on at INFO (no env flag). One WhatsApp message produces a correlated chain:

| Event | Meaning |
|-------|---------|
| `stt_ok` | Voice transcript after STT |
| `route` | Pipeline chosen (`pipeline=agent`) |
| `turn_start` | Agent session snapshot (stage, restaurant, cart) |
| `prefetch` | Offers/restaurants/menu loaded into context |
| `llm_request` | Text sent to DeepSeek (last user message) |
| `llm_tool` | Tool call + result preview |
| `llm_reply` | Final assistant text |
| `turn_end` | Agent turn complete |

Voice inbound also logs `abuu_wa_trace IN type=voice text=...` **after** STT with the transcript (not `[voice-note]`).

Recent history without follow:

```bash
./scripts/vps-abuu-live-trace.sh --history 50
```

**Full STT diagnostic on VPS:**

```bash
chmod +x scripts/vps-abuu-voice-stt-check.sh
./scripts/vps-abuu-voice-stt-check.sh
```

**Note:** Customer-stated `allergy_note` on an order is separate from item-level `allergen_tags_json` on menu items. The waiter captures the note at confirm time; tags drive search safety.

Future cities: add rows to `abuu_market_agents` and set `ABUU_MARKET_AGENT`.
