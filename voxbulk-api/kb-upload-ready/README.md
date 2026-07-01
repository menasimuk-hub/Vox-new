# VOXBULK voice KB upload pack

Upload these files to test the fixed voice prompt behaviour (no script repetition, human interrupt handling).

## Lead (Jode — website Talk to us)

| File | Where it goes |
|------|----------------|
| `lead/jode-system-prompt.md` | Admin → **Talk to us / Lead agent prompt** → paste into **System prompt** textarea (do NOT use "Use KB as prompt" for this file) |
| `lead/services-facts-no-pricing.md` | Upload to KB with scope **lead** → tick ONLY this file in the KB table |

**Suggested Telnyx greeting (Greeting field):**

> Hi {{first_name}}, I'm Jode from VOXBULK — thanks for getting in touch. This call is recorded for quality; privacy details are on voxbulk.com. How can I help you today?

Then **Save settings** → **Resync Telnyx**.

## Interview (regional English phone AI — Leo, Jode, US/CA/AU/IE/SC)

| Step | Command / action |
|------|------------------|
| 1. Migrate | `alembic upgrade head` (adds `accent_region`, `gender` on agents) |
| 2. Seed DB | `python scripts/seed_interview_regional_agents.py` |
| 3. Provision Telnyx | `python scripts/provision_interview_telnyx_assistants.py --dry-run` then without `--dry-run` |

**KB files** (auto-loaded into agent `kb_context` by seed script):

| File | Purpose |
|------|---------|
| `interview/interview-conduct-base.md` | Shared interview rules |
| `interview/interview-region-accent-{GB,SC,IE,US,CA,AU}.md` | Regional accent notes |

**Optional `.env` voice mapping** (ElevenLabs composite IDs from Telnyx):

- `INTERVIEW_TELNYX_MODEL=openai/gpt-4o` (optional; defaults to Leo's model)
- `INTERVIEW_TELNYX_ASSISTANT_ID_GB_LEO=assistant-...` (Leo — existing)
- `INTERVIEW_VOICE_{GB,SC,IE,US,CA,AU}_{MALE,FEMALE}=ElevenLabs.eleven_flash_v2_5.{voice_id}`

Telnyx portal names follow: `VOXBULK Interview {REGION} {Name} {M|F}`.

**Note:** Website **Jode** (Talk to us) is separate from interview **Jode** (`interview-gb-jode`).

## Sales (Adam — outbound)

| File | Where it goes |
|------|----------------|
| `sales/adam-system-prompt.md` | Admin → **Lead sales → Sales setup** → paste into **Master sales script** |
| `sales/pricing-and-offers.md` | Upload to KB with scope **sales** → tick ONLY this file in the KB table |

**Suggested Telnyx greeting:**

> Hi {{first_name}}, it's Adam from VOXBULK following up on your chat with Jode — is now still a good time? This call is recorded for quality; see voxbulk.com for privacy.

Then **Save settings**. On each sales lead click **Regenerate prompt** once after changing master/KB.

## After upload checklist

1. Delete old dialogue-style KB files (jode_talk.md, Adam.md) from lead/sales libraries if still present.
2. Clear old system prompt text before pasting new templates.
3. Save settings and confirm Telnyx preview char counts look reasonable (~1–3k for master, not a 6-line script).
4. Test interrupt: ask a random question mid-call — agent should answer it, not restart the opening.
