# Customer Feedback service

## Audit summary (vox-connect-suite-main vs voxbulk.com)

| Area | vox-connect-suite-main | voxbulk.com (before) | voxbulk.com (after) |
|------|------------------------|----------------------|---------------------|
| Backend / DB | None (UI prototype) | None | `feedback_*` tables, APIs |
| Admin UI | None | None | `/customer-feedback/*` admin pages |
| Dashboard UI | `/feedback/*` mock | None | `/feedback/*` wired to API |
| Industries / types | Hardcoded in wizard | WA Survey only (separate) | `feedback_industries`, `feedback_survey_types` |
| Billing | Shared mock GBP | Single org subscription | Parallel `service_code=customer_feedback`, GC-only |
| WhatsApp | Client QR + wa.me | Survey order flow only | Trigger router on inbound |
| Results | Reuses survey results | N/A | Per-location filters |

Design reference: `vox-connect-suite-main/src/routes/_app.feedback.*.tsx` — layout copied into dashboard-web.

## GoCardless notes

- Feedback subscriptions use Direct Debit only (no wallet top-up, no overage).
- Plans are grouped by market zone (`gb`, `us`, `ca`, `au`) with `PlanPrice` multi-currency rows.
- Enable non-UK packages only after your GoCardless merchant account supports the target scheme/currency.

## Invoice stream

Feedback subscription invoices use prefix `CF-` and `billing_invoices.service_code = customer_feedback`.

## QR trigger format

```
Hi! I'd like to share feedback for {company} at {branch}. acme-marylebone-a3f2b1
```

- Plain text only (no emojis) for reliable WhatsApp pre-fill on all devices.
- Reference code at the end: `company-branch-xxxxxx` (6-character suffix).
- Inbound handler parses that code → location → survey flow.
- Legacy `[ref:token]` messages still work.

## Test push one template to Telnyx (CLI)

After importing templates and configuring Telnyx (API key + WhatsApp Business Account ID):

```bash
cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
python scripts/push_feedback_template_to_telnyx.py --template-key thank_you --dry-run
python scripts/push_feedback_template_to_telnyx.py --template-key thank_you
```

Use `--template-id UUID` for a specific row. Errors from Telnyx/Meta are printed to stderr with full JSON detail.

## Test push all templates for one industry (CLI)

Push every survey template for an industry (e.g. Fitness & gyms = 20 templates):

```bash
cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
python scripts/push_feedback_industry_to_telnyx.py --industry-slug fitness --dry-run
python scripts/push_feedback_industry_to_telnyx.py --industry-slug fitness
```

Slugs: `restaurant`, `retail`, `salon`, `hotel`, `fitness`, `events`, `others`.

## Arabic templates (OpenAI + Telnyx)

Translate all English templates to Arabic and optionally push to Telnyx:

```bash
cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
python scripts/translate_feedback_templates_to_ar.py --dry-run --limit 3
python scripts/translate_feedback_templates_to_ar.py --push-telnyx
python scripts/translate_feedback_templates_to_ar.py --industry-slug fitness --force --push-telnyx
```

Uses **OpenAI structured JSON API** by default (`Admin → Integrations → OpenAI`).  
Leading emoji from English templates is kept at the **start** of the Arabic body (never mid-sentence).  
Optional: `--provider deepseek` for DeepSeek chat fallback.

**Runtime language:** Arabic templates are sent when the visitor’s number uses an Arabic-region country code (`+966`, `+971`, `+20`, `+962`, etc.), or for testing append `(ar)` to the QR trigger message:

`Hi! I'd like to share feedback for Acme at Downtown. acme-downtown-a3f9k2 (ar)`

Survey questions and buttons are in the visitor’s language. **Dashboard results are always stored and shown in English** (`answer_text_en`); the original reply is kept in `original_text`.

## Workflow (QR → results)

```
QR scan → visitor sends trigger → charge 1 unit (per inbound) → selected topics (1–6)
→ optional open question → optional marketing opt-in → thank-you (on completion) → English results in dashboard
```

- **Edit survey after launch:** Dashboard → Saved QR surveys → **Edit survey** (topics + closing toggles). QR token unchanged — reprint not required unless you duplicate to a new location.
- **Template wording:** Admin → Customer feedback → Survey types / WhatsApp templates. Topic and system template text must be approved on Meta/Telnyx before WhatsApp delivery.
- QR codes use **Admin → Integrations → Telnyx → WhatsApp From** (same number as survey/interview WhatsApp).
- On seed/API boot, that number is copied into `feedback_wa_senders` for QR generation.
- Admin sync: `POST /admin/customer-feedback/wa-senders/sync-from-telnyx`
- **Survey language** — detected from visitor phone country code (English templates for now).
- **Results** — stored with `answer_text_en` for dashboard display.
- **Billing** — 1 WA unit per inbound QR trigger (not per completed survey).

## Package tiers (seed)

| Plan | Locations | Triggers/mo |
|------|-----------|-------------|
| Starter | 1 | 1,000 |
| Pro | 5 | 3,000 |
| Business | 20 | 10,000 |

Promo sends (future) deduct from org **promo wallet** at `promo_message_cost_minor` per message.

## Admin UI

| Route | Purpose |
|-------|---------|
| `/customer-feedback/industries` | Industry list + import English templates |
| `/customer-feedback/industries/:id` | Industry edit + survey types |
| `/customer-feedback/survey-types/:id` | Topic template editor |
| `/customer-feedback/packages` | Multi-currency plan pricing |

## Post-deploy (VPS)

1. Migration **`0119_customer_feedback_workflow`** (`alembic upgrade head`).
2. Admin → Industries → **Import English templates** (140 topic templates + system templates).
3. **Push system closing templates to Telnyx/Meta** (required for open question, marketing opt-in, and thank-you):

```bash
cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
for key in open_question marketing_opt_in thank_you tell_us_more; do
  python scripts/push_feedback_template_to_telnyx.py --template-key "$key"
done
```

Wait for Meta approval; confirm `telnyx_sync_status` is `approved` / `synced` / `live` in Admin.

4. **Backfill legacy locations** (created before `survey_config_json` was stored):

```bash
python scripts/backfill_feedback_survey_config.py --dry-run
python scripts/backfill_feedback_survey_config.py
```

New scans also auto-repair stale config on first trigger (lazy repair in the WhatsApp handler).

5. Optional: per-industry **Sync to Telnyx** for topic templates.

## Troubleshooting WhatsApp testing

### `feedback_wa_template_not_approved … status=draft`

This is **not a queue block**. Customer Feedback runs synchronously on each inbound webhook — there is no Celery job for the chat flow.

The warning means the `thank_you` (or other) template row exists in the DB but **`telnyx_sync_status` is still `draft`** — Meta/Telnyx has not approved it yet, so the thank-you send may fail.

Fix:

```bash
cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
python scripts/push_feedback_template_to_telnyx.py --template-key thank_you
# wait for Meta approval, then confirm telnyx_sync_status is approved/synced/live in Admin
```

Until approved, the survey can **complete in the DB** but the final WhatsApp message may not deliver.

### Clear stuck session for your test phone

If every inbound message is treated as a survey answer (or you want a clean retest):

```bash
cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
python scripts/clear_feedback_wa_state.py --phone +447954823445 --dry-run
python scripts/clear_feedback_wa_state.py --phone +447954823445
```

If you previously tested another product on the same number, flush any stale Redis session keys for that phone before retesting feedback.

### Telnyx opt-out (`block rule`)

If logs show `Messages cannot be sent … due to an existing block rule`, send **`UNSTOP`** to the WhatsApp sender number on WhatsApp. Telnyx cannot remove this via API.

### Celery (voice notes only)

Feedback chat does **not** use Celery. Only **survey voice-note transcription** tasks run in the worker. To inspect:

```bash
./vox.sh status   # shows celery worker
redis-cli LLEN celery   # pending tasks (if using default queue)
```

Restart worker after deploy: `./vox.sh restart`

### Web survey voice notes (STT + translation)

Customer Feedback **web** voice notes are transcribed **inline** in the API (not Celery). Pipeline:

1. Browser uploads `webm` → ffmpeg transcode to mono 16 kHz Ogg (requires `ffmpeg` on PATH)
2. STT provider order (web): `deepinfra` → `deepgram` → `whisper_cpp` → `groq` (override with `VOICE_STT_PROVIDER_ORDER` for WhatsApp inbound only)
3. Detected language from STT drives English translation; results store `answer_text_en` + `original_text`

**VPS checks after deploy:**

```bash
which ffmpeg ffprobe
# Admin → Integrations: DeepInfra and/or Deepgram configured
# Admin → Integrations: DeepSeek/OpenAI for translation
```

Test: open `/survey/{qr_token}`, record a voice note in Spanish → dashboard **Customer feedback results** should show English transcript and **Original:** line.

## Known gaps (not yet shipped)

| Gap | Notes |
|-----|--------|
| Telnyx Meta template push | Templates stored as draft; sync sets `submitted` only |
| Promo wallet top-up | Models exist; no Stripe/Airwallex top-up or send UI |
| 50-language templates | English MD import only (Track K) |
| Dashboard step 3 QR | Local preview QR; step 4 uses API preview with real trigger |
| Hub vs dedicated routes | Subscriptions/locations/results still on `CustomerFeedbackHub` tabs |
| GoCardless non-GB | Enable EU/US/CAD/AUD only when GC merchant supports scheme |
