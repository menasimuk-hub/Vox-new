# Provider integration strategy (voxbulk-api)

Audit based on existing code only — no greenfield redesign.

**Codebase:** `voxbulk-api`  
**Date:** 2026-05-17

---

## A. Current provider architecture summary

### Central registry

- `ProviderSettingsService` (`app/services/provider_settings.py`) stores **encrypted platform JSON** per provider key, including **`twilio`**, **`telnyx`**, **`vapi`**, and the AI stack (`openai`, `azure_speech`, `groq`, `deepgram`, `cartesia`, etc.), with per-provider required fields and secret key sets.

### `app/services/providers/*`

- Mostly **AI/STT/TTS** helpers (`openai_service.py`, `deepgram_service.py`, …).
- `providers/telnyx_service.py` is a **thin re-export** of `TelnyxExecutionService` / `TelnyxVoiceAdapter` from `telnyx_voice_service.py` — not a separate telephony abstraction layer.

### Twilio (`twilio_service.py`)

- **`TwilioAdapter`**: real **REST outbound** `POST https://api.twilio.com/.../Calls.json` (`start_outbound_call`), with class docstring stating Twilio is **legacy for new active outbound voice** while **Telnyx + Azure Speech + OpenAI** are the new voice runtime — yet **`call_tasks.process_recovery_job` still calls `TwilioAdapter`** for recovery.
- **`TwilioWhatsAppAdapter`**: used from **`call_tasks`** as fallback when voice fails.
- **`TwilioExecutionService` / `TwilioCallerIdService`**: webhook logging and Twilio caller-ID flows used from **`app/routers/twilio.py`**.

### Telnyx (`telnyx_voice_service.py`)

- **`TelnyxVoiceAdapter`**: **REST** `POST https://api.telnyx.com/v2/calls` with `connection_id`, optional `webhook_url`, `status_callback_url`, `stream_url` / `stream_track`.
- **`TelnyxExecutionService.start_call`**: creates **`CallLog`** with `provider="telnyx"`, `external_call_id` = Telnyx call id, wires **agent** via `AgentManager.resolve_agent`, embeds **`client_state`** JSON (`org_id`, `user_id`, etc.).
- **`TelnyxExecutionService.log_call_event`**: updates **`CallLog`** from **JSON** webhook payloads (and can create a log from `client_state` / header org).
- **`TelnyxCallerIdService`**: Telnyx **verified numbers** API + webhook `mark_webhook`.

### Vapi (`vapi_service.py`)

- **`VapiAdapter.start_call`** returns **`"not_implemented"`** with explicit comment that **Vapi is not the active voice runtime**.

### Voice / AI agent (`voice_agent_service.py`)

- **`AzureSpeechService`** + **`OpenAICallReasoningService`** + **`VoiceAgentService`**: TTS/STT + chat completion over **platform `ProviderSettings`** (`azure_speech`, `openai`) — **independent of which carrier** carries audio, as long as media reaches the app.

### Workers

- **`call_tasks.process_recovery_job`**: loads **`twilio`** config, outbound **`TwilioAdapter.start_outbound_call`**, writes **`CallLog(provider="twilio")`**, optional **`TwilioWhatsAppAdapter`**, **`RecoveryJob.provider`** set to **`twilio`** / **`twilio_whatsapp`**.
- **`sync_tasks.handle_twilio_webhook`**: parses **Twilio form-encoded** webhook bodies from **`webhook_events`**, updates **`CallLog`** by `external_call_id`, **`RecoveryJob`** where `provider == "twilio"` (and WhatsApp jobs `twilio_whatsapp`), drives **`RecoveryStateMachine`**.
- **`handle_vapi_webhook`**: marks event processed only — **no business logic**.

### Webhooks / routers

| Router | Paths | Auth | Async | Primary tables |
|--------|-------|------|-------|----------------|
| `webhooks.py` | `/webhooks/twilio`, `/webhooks/vapi`, `/webhooks/gocardless` | Twilio / Vapi HMAC / GoCardless HMAC | Celery for Twilio/Vapi/GoCardless | `webhook_events` → worker |
| `twilio.py` | `/twilio/webhooks/whatsapp`, `/calls`, `/caller-id` | Twilio signature | **Synchronous** on `/calls` for recovery | `CallLog`, `RecoveryJob`, `Appointment` |
| `telnyx.py` | `/telnyx/webhooks/*`, `/telnyx/media-stream` | **No signature in code** | Sync HTTP; WebSocket for media | `CallLog`, `AgentManager` |

### Tenant isolation

- Recovery path: **`org_id`** on **`RecoveryJob` / `Appointment`** (Celery loads job scoped to org).
- Telnyx agent path: **`org_id`** on **`CallLog`** and/or **`client_state`** / header **`X-Retover-Org-Id`** in `log_call_event`; media stream resolves org from **`CallLog`** row.

---

## B. Best option for this codebase

**E. Hybrid: telephony provider + AI agent provider**

The repo **already implements** that split in code:

- **Twilio** → recovery campaign pipeline (Celery + `RecoveryJob` + form webhooks + WhatsApp fallback)
- **Telnyx** → programmable voice + streaming agent turns (REST dial + JSON webhooks + WebSocket + `AgentManager`)
- **AI** → centralized in **`ProviderSettingsService`** + **`voice_agent_service`** / **`agents`**

---

## C. Why the other options are worse (for this tree)

| Option | Fit / reuse | Webhooks / campaigns | Risk |
|--------|-------------|----------------------|------|
| **A. Standardize on Twilio** | **Poor**: marginalizes **`TelnyxExecutionService`**, **`/telnyx/media-stream`**, and Telnyx REST dial — the main **interactive** voice path today. | Twilio fits **recovery** already; rebuilding Telnyx-style streaming + agent loop on **Twilio Media Streams** is **not present** — large new surface. | High: rewrite agent transport + duplicate AI wiring. |
| **B. Standardize on Telnyx** | **Medium**: Telnyx outbound + logging is strong, but **recovery** is **hard-wired** to **`TwilioAdapter`** / **`provider == "twilio"`** in **`call_tasks`** and **`sync_tasks`**. | Would need **Telnyx** equivalents for **recovery** + **WhatsApp** semantics and to **replace or merge** Twilio webhook paths. | Medium–high: migration of **`RecoveryJob`**, **`handle_twilio_webhook`**, **`routers/twilio.py`**, tests. |
| **C. Standardize on Vapi** | **Very poor**: **`VapiAdapter`** is a **stub**; no outbound implementation. | **`handle_vapi_webhook`** is effectively a no-op. | Extreme: build from near-zero in this repo. |
| **D. Add Teli (new provider)** | **Poor**: third carrier alongside Twilio + Telnyx **without** removing duplication; **no** `teli` entry in **`ProviderSettingsService.PROVIDERS`** today. | New signature model, new REST client, new webhooks, new ops. | High operational complexity, low reuse vs finishing the two existing stacks. |

---

## D. Exact implementation plan (extend E, do not greenfield)

**Principle:** Keep **Twilio = recovery / WhatsApp / Twilio-signed ingestion** and **Telnyx = conversational outbound + media + JSON webhooks**; keep **AI** behind **`ProviderSettingsService`** + existing **`VoiceAgentService` / `AgentManager`**.

### Files to modify

1. **`app/routers/telnyx.py`**
   - Add **Telnyx webhook signature verification** before `log_call_event`.
   - Optionally require **`X-Retover-Org-Id`** or **`client_state.org_id`** for routes that create new `CallLog` rows.

2. **`app/routers/twilio.py`** and **`app/workers/sync_tasks.py`** (and optionally **`webhooks.py`**)
   - **Document and reduce duplication**: `/twilio/webhooks/calls` updates **`RecoveryJob`** inline while `/webhooks/twilio` → Celery does similar work — pick **one primary path** (typically Celery for durability) and make the other thin (log-only).
   - Extract shared logic into a small module (below).

3. **`app/services/twilio_service.py`**
   - Align docstrings with reality: recovery remains Twilio by design under hybrid **E**, or add a TODO tied to **`call_tasks`** if migrating later.

4. **`app/workers/call_tasks.py`**
   - Optional: structured log `campaign_channel=recovery_twilio`.
   - **Later only:** branch on org/feature flag to call **`TelnyxVoiceAdapter`** with `client_state` including `org_id`.

5. **`app/services/recovery_service.py`** or new **`app/services/telephony_recovery_bridge.py`**
   - Pure function e.g. `apply_twilio_call_status_to_recovery(db, *, call_sid, call_status, raw_body)` used by **`sync_tasks`** and optionally **`routers/twilio.py`**.

6. **`README.md`** (or this doc)
   - Table: URL, provider, auth, async (Celery?), tables updated.

### Files to create

- **`app/services/telephony_recovery_bridge.py`** — shared Twilio call-status → **`RecoveryJob` / `Appointment` / `CallLog`** mapping.
- **Optional:** **`app/core/telnyx_webhook_security.py`** — Telnyx signature verification only.

### Interfaces to reuse

- **`ProviderSettingsService.get_platform_config_decrypted`** — config seam for Twilio and Telnyx.
- **`TelnyxVoiceAdapter.start_outbound_call`** / **`TelnyxExecutionService.start_call`** — Telnyx leg.
- **`TwilioAdapter` / `TwilioWhatsAppAdapter`** — recovery leg.
- **`AgentManager` + `AgentRunRequest` / `AgentRuntimeContext`** — agent leg (`telnyx` router).
- **`VoiceAgentService` / `AzureSpeechService`** — STT/TTS/LLM for media stream.
- **`TelnyxProviderResult` / `ProviderResult`** — keep parallel result types unless you later extract a `Protocol`.

### DB changes

- **None required** to formalize **E** today: **`RecoveryJob.provider`** is already a string (default `twilio`); **`CallLog.provider`** distinguishes `twilio` vs `telnyx`.
- **Optional later:** Alembic if you add per-org feature flags for recovery carrier.

### Webhook changes

- **Telnyx:** signature verification on **`POST /telnyx/webhooks/*`**; align stored **`telnyx`** config URLs (`voice_webhook_url`, `status_callback_url`, `media_stream_url`) with those routes.
- **Twilio:** single owner of recovery transitions (`/webhooks/twilio` vs `/twilio/webhooks/calls`) to prevent double application.

### Celery task changes

- **Minimum for E:** no change to **`process_recovery_job`** if Twilio remains the recovery carrier.
- **If deduplicating Twilio recovery:** move logic into **`telephony_recovery_bridge`**; **`handle_twilio_webhook`** imports it; **`/twilio/webhooks/calls`** calls the same helper or enqueues a small task — prefer one code path.

---

## E. Risks and cleanup needed first

1. **Duplicate Twilio recovery paths** — `routers/twilio.py` (`/twilio/webhooks/calls`) and `sync_tasks.handle_twilio_webhook` (fed by `/webhooks/twilio`) can both touch **`RecoveryJob` / `Appointment`**; risk of race or inconsistent ordering. Clean up before scaling traffic.

2. **Telnyx HTTP webhooks are unsigned in code** — `telnyx.py` accepts JSON with no verification; higher spoofing risk than Twilio routes. Fix before production.

3. **Doc vs behavior drift** — `TwilioAdapter` doc says new outbound uses Telnyx, but `call_tasks` still uses Twilio for recovery; `VapiAdapter` is stub while `/webhooks/vapi` exists. Clarify in docs or implement/remove Vapi path.

4. **Operational complexity of E** — two carriers, two webhook stacks, Celery for Twilio `webhook_events` only. Mitigation: runbook + env checklist for `ProviderSettingsService` required keys for `twilio` vs `telnyx`.

5. **Vapi surface** — provisional signature in `webhooks.py`; worker noop — either implement or disable in deployment config.

---

## Evidence file list

| Topic | Files |
|-------|--------|
| Provider registry | `app/services/provider_settings.py` |
| Twilio | `app/services/twilio_service.py`, `app/routers/twilio.py` |
| Telnyx | `app/services/telnyx_voice_service.py`, `app/services/providers/telnyx_service.py`, `app/routers/telnyx.py` |
| Vapi | `app/services/vapi_service.py`, `app/routers/webhooks.py` |
| AI / voice agent | `app/services/voice_agent_service.py`, `app/services/agents/manager.py` |
| Recovery worker | `app/workers/call_tasks.py` |
| Webhook worker | `app/workers/sync_tasks.py` |
| Recovery model | `app/models/recovery_job.py` |
| Call logs | `app/models/call_log.py` |
