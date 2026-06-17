# Phase 2 — Abuu Agent Phase 1 Rollout Runbook

**Scope:** validation, trace review, and rollback only. No product-logic changes unless a critical blocker appears during live tests.

**Context:** Phase 1 orchestration is behind `ABUU_AGENT_PHASE1_ORCHESTRATION`. Local tests passed: `test_abuu_agent_phase1.py`, `test_abuu_agent.py`, `test_abuu_voice_order_debug.py`.

**Pilot IDs:**
- Fast food: `abuu-rest-fastfood` — **وجبات سريعة**
- Fish: `abuu-rest-fish` — **مطعم البحر** / Al-Bahr Seafood

---

## Ownership

| Role | Responsibility |
|------|----------------|
| **Flag owner** | Pilot lead — enables Phase 1 on VPS after `git pull` + local tests pass. |
| **Rollback authority** | Same person — flips flag OFF on any rollback trigger; escalate if non-test customers are affected. |
| **Trace reviewer** | Inspects Stage 5/6 and `abuu_agent_trace` logs after each of the 5 live tests. |

**Only the flag owner edits `voxbulk-api/.env` on VPS.** Do not enable globally until GO criteria in Section 5 are met.

**Important:** Stages **2 / 5 / 6** populate only for **WhatsApp voice notes** when `ABUU_VOICE_ORDER_DEBUG=true`. Typed text validates replies and logs but not full debug stages.

---

## 0. Pre-rollout: validate flag OFF (baseline)

| Step | Action |
|------|--------|
| Env | `ABUU_AGENT_PHASE1_ORCHESTRATION=false`, `ABUU_AGENT_WAITER_MODE=false`, `ABUU_VOICE_ORDER_DEBUG=true` |
| Restart | `cd /www/voxbulk && ./vox.sh restart` |
| Send | Voice: `وجبات سريعة، ايش المنيو تاع الوجبات السريعة؟` |
| **PASS (OFF)** | Debug row created; stages 5/6 may show LLM/tool path (not `phase1_deterministic`); system responds |
| **FAIL (OFF)** | No debug row for voice, API down, or no reply → fix infra before Phase 1 ON |

Record one OFF trace ID as baseline (required for postmortem handoff). Then proceed to Section 1.

**Save baseline ID:**
```bash
python3 scripts/abuu_voice_order_debug.py latest   # copy to run log
```

---

## 1. VPS enable checklist

### Pull + env (internal test line only)

```bash
cd /www/voxbulk
git pull origin main
```

Edit `voxbulk-api/.env`:

```bash
ABUU_AGENT_PHASE1_ORCHESTRATION=true
ABUU_AGENT_WAITER_MODE=false
ABUU_AGENT_ENABLED=true
ABUU_CONVERSATION_MODE=agent
ABUU_VOICE_ORDER_DEBUG=true
```

### Restart

```bash
cd /www/voxbulk
./vox.sh restart
```

### Inspect traces

```bash
cd /www/voxbulk/voxbulk-api && source .venv/bin/activate

python3 scripts/abuu_voice_order_debug.py latest
python3 scripts/abuu_voice_order_debug.py show <order_request_id>

grep abuu_agent_trace /www/voxbulk/voxbulk-api/logs/*.log | tail -80
# or: journalctl -u voxbulk-api -n 200 --no-pager | grep abuu_agent_trace
```

**Correlation ID:** For voice, `correlation_id` in logs = WhatsApp `message_id` when present, else `order_request_id` from debug `begin`. Same value must appear on `turn_start`, `state_before`, `state_after`, and `turn_end` for that turn.

---

## 2. Live test messages (5 voice notes, in order)

Wait for reply between each test.

### Test 1 — Exact restaurant + menu

| | |
|--|--|
| **Send** | `وجبات سريعة، ايش المنيو تاع الوجبات السريعة؟` |
| **Reply PASS** | Arabic fast-food menu (e.g. برجر); not fish/chicken |
| **Stage 5 PASS** | `parse_status=ok`, `branch=phase1_select_and_menu`, `restaurant_id=abuu-rest-fastfood`, `tool_calls=[]` |
| **Stage 6 PASS** | `requested/active=abuu-rest-fastfood`, `restaurant_match=true`, `status=draft` |

**Record after each test:** `python3 scripts/abuu_voice_order_debug.py latest` → save `order_request_id` in run log (Tests 1–5 + baseline OFF).

### Test 2 — Switch from stale/bound restaurant

| | |
|--|--|
| **Setup** | After Test 1 or prior fish cart |
| **Send** | Same as Test 1 |
| **Reply PASS** | Fast-food menu; optional `تم تفريغ السلة...` if cart existed |
| **Stage 5/6 PASS** | Same as Test 1; neither ID is `abuu-rest-fish` |

### Test 3 — Category only, no restaurant

| | |
|--|--|
| **Setup** | `yallasay` / `يلا ساي` to clear |
| **Send** | `بدي برجر` |
| **Reply PASS** | Asks which restaurant; no full menu |
| **Stage 5 PASS** | `restaurant_id` null, no `max_turns_exceeded` |
| **Stage 6 PASS** | Absent or `requested_restaurant_id` null |

### Test 4 — Reset phrase

| | |
|--|--|
| **Send** | `اعرض المطاعم` |
| **Reply PASS** | Numbered restaurant list |
| **Stage 5 PASS** | `ok` or successful list/change tools; not blocked on this phrase |
| **Stage 6** | Empty OK after reset |

### Test 5 — Numeric restaurant pick

| | |
|--|--|
| **Setup** | Immediately after Test 4 list |
| **Send** | List number for **وجبات سريعة** (often `4` — confirm from list text) |
| **Reply PASS** | Confirms fast food |
| **Stage 6 PASS** | `requested/active=abuu-rest-fastfood`, `restaurant_match=true` |

---

## 3. Stage verification checklist

### Stage 2
- **PASS:** Non-empty transcript matching speech; contains `وجبات سريعة` on Tests 1/2
- **FAIL:** Empty, 16-digit WA ID, or unrelated garbage

### Stage 5
- **PASS:** `parse_status=ok`, `parse_error=null` on happy path; `branch=phase1_select_and_menu` on Tests 1–2; no `change_restaurant({})` in `tool_calls` on deterministic paths
- **FAIL:** `max_turns_exceeded`, wrong `restaurant_id`, speculative tool chains

### Stage 6
- **PASS:** `requested_restaurant_id` + `active_order_restaurant_id` match on Tests 1, 2, 5; `restaurant_match=true`
- **FAIL:** Fish ID when user asked fast food; `cancelled` after menu-only Tests 1/2

### Logs
- **PASS:** One `correlation_id` per voice turn across `turn_start` → `state_before/after` → `turn_end`
- **FAIL:** Missing correlation on >1 of 5 tests; session mutated after `blocked=true`

---

## 4. Rollback criteria and procedure

### Rollback triggers (any one → rollback immediately)

1. Wrong restaurant binding (user asked fast food, stage 6 shows fish or other pilot).
2. Cart cleared without explicit restaurant switch in user message.
3. `max_turns_exceeded` on Tests 1 or 2 with Phase 1 ON.
4. `restaurant_match: false` on happy-path Tests 1, 2, or 5.
5. `change_restaurant({})` in stage 5 **and** session/restaurant state changed.
6. Missing `correlation_id` / `turn_start` on two consecutive voice tests.

### Before rollback — capture (required)

Run **before** setting the flag OFF. Paste output into incident notes / Slack / ticket.

**Capture list:**
- UTC timestamp
- Env grep: `ABUU_AGENT_PHASE1`, waiter mode, debug, conversation mode
- `order_request_id` from `latest`
- Full `show` JSON → `/tmp/abuu-rollback-trace.json`
- User message from STT (stage 2) / Stage 3
- Correlation hint from bundle (`message_id`)
- Last 50 `abuu_agent_trace` lines

```bash
cd /www/voxbulk/voxbulk-api && source .venv/bin/activate

echo "=== UTC $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "=== ENV (Phase 1 flags) ==="
grep -E 'ABUU_AGENT_PHASE1|ABUU_AGENT_WAITER|ABUU_VOICE_ORDER_DEBUG|ABUU_CONVERSATION_MODE' /www/voxbulk/voxbulk-api/.env

ORDER_ID=$(python3 scripts/abuu_voice_order_debug.py latest)
echo "order_request_id=$ORDER_ID"
python3 scripts/abuu_voice_order_debug.py show "$ORDER_ID" > /tmp/abuu-rollback-trace.json

echo "=== User message (from stage 2 or 3) ==="
python3 -c "
import json, sys
d=json.load(open('/tmp/abuu-rollback-trace.json'))
print('STT:', (d.get('stages') or {}).get('2_stt_raw', {}).get('transcript'))
msgs=(d.get('stages') or {}).get('3_llm_prompt', {}).get('messages') or []
for m in reversed(msgs):
    if m.get('role')=='user':
        print('USER:', m.get('content')); break
"

echo "=== correlation_id hint (message_id from debug row) ==="
python3 -c "
import json
d=json.load(open('/tmp/abuu-rollback-trace.json'))
print('message_id:', d.get('message_id'))
"

echo "=== Last 50 abuu_agent_trace lines ==="
grep abuu_agent_trace /www/voxbulk/voxbulk-api/logs/*.log 2>/dev/null | tail -50 \
  || journalctl -u voxbulk-api -n 500 --no-pager | grep abuu_agent_trace | tail -50
```

### Postmortem handoff (after rollback or failed run)

Complete before closing the incident or ending the pilot session:

- [ ] **Baseline OFF trace saved** (Section 0 `order_request_id`)
- [ ] **Five voice tests recorded** — one `order_request_id` per test (Tests 1–5)
- [ ] **Any failure trace exported** — `/tmp/abuu-rollback-trace.json` or `show <id>` for failing turn
- [ ] **Rollback reason noted** — which trigger from Section 4 (numbered)
- [ ] **Next action assigned** — e.g. fix + retest, keep flag OFF, or escalate to engineering

### Rollback action

**Rollback authority** executes:

```bash
# Edit voxbulk-api/.env
ABUU_AGENT_PHASE1_ORCHESTRATION=false

cd /www/voxbulk
./vox.sh restart
```

### Confirm rollback

1. Voice: `وجبات سريعة، ايش المنيو تاع الوجبات السريعة؟`
2. **PASS:** No `branch=phase1_select_and_menu` in stage 5; pre-Phase-1 behavior restored.
3. **FAIL:** Still deterministic → wrong `.env` or restart did not apply.

No DB migration rollback (flag-only).

---

## 5. Go / no-go

### GO — wider internal use (flag stays ON)

- Tests 1, 2, 5 pass stage 5 + 6
- Test 3 does not write restaurant ID
- Test 4 lists restaurants without block/fallback
- Zero rollback triggers across **two** full runs (same day)
- Flag OFF baseline (Section 0) still works

### NO-GO — test line only

- Any rollback trigger fired
- Test 1/2 still `max_turns_exceeded` with Phase 1 ON
- Stage 6 `restaurant_match: false` on happy-path menu request
- Correlation missing on >1 of 5 tests

### Production

Do not enable globally until internal GO + post-deploy Test 1 voice check after `./deploy-vps.sh`.

---

## 6. Flag cleanup

After **at least 2 weeks** stable on the internal pilot with **zero rollbacks**:

- [ ] Create follow-up task: **remove or fold `ABUU_AGENT_PHASE1_ORCHESTRATION`**
- [ ] Make deterministic gate + tool guards the default path; delete dual OFF/ON branches
- [ ] Keep regression tests (`test_abuu_agent_phase1.py`); remove flag from docs and `.env` examples

Stale flags become permanent `if phase1` branches — schedule cleanup before widening rollout.

---

## Quick reference — env matrix

| Variable | Internal validation | Production default |
|----------|---------------------|-------------------|
| `ABUU_AGENT_PHASE1_ORCHESTRATION` | `true` | `false` |
| `ABUU_AGENT_WAITER_MODE` | `false` | unchanged |
| `ABUU_VOICE_ORDER_DEBUG` | `true` | `false` |
| `ABUU_CONVERSATION_MODE` | `agent` | `agent` |

**Untouched:** waiter_v2, payment, Telnyx routing.

---

## Before/after (Test 1 reference)

| Stage | Before Phase 1 | After Phase 1 ON (PASS) |
|-------|----------------|-------------------------|
| 2 STT | `وجبات سريعة...` | Same |
| 5 | `fallback`, `max_turns_exceeded`, `change_restaurant({})` chain | `ok`, `phase1_deterministic`, `abuu-rest-fastfood`, `tool_calls=[]` |
| 6 | `abuu-rest-fish`, often `cancelled` | `requested/active=abuu-rest-fastfood`, `restaurant_match=true` |

---

## Next step

**Execute on VPS now.** Collect traces; no more planning until one full 5-test pass is recorded.

1. Section 0 — OFF baseline (save `order_request_id`)
2. Section 1 — enable Phase 1 + restart
3. Section 2 — five voice tests (save each `order_request_id`)
4. Section 5 — GO / NO-GO decision

---

## Verdict

Runbook is ready for **internal pilot execution**. Progressive rollout structure: small cohort → verify success criteria → kill switch ready. The bug class (state leakage, wrong restaurant binding) requires stage 5/6 + correlation log verification — not reply-only smoke tests.

**Next action:** VPS run today. Flag owner executes; trace reviewer validates; save six IDs minimum (1 baseline OFF + 5 tests ON).
