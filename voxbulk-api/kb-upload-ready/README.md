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
