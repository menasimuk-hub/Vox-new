# Telnyx WhatsApp templates — copy & paste (with icons)

Use **English (UK)** / `en_GB` for every template. Names must match **exactly** (lowercase, underscores).

In Telnyx: **Messaging → WhatsApp → Templates → Create template**

For each `{{1}}`, `{{2}}`, etc. add the **sample value** shown — Meta rejects templates without examples.

---

## Template 1 — `voxbulk_sales_opt_in`

| Field | Value |
|-------|--------|
| **Name** | `voxbulk_sales_opt_in` |
| **Category** | Marketing |
| **Language** | English (UK) |

**Header** (optional · Text):
```
👋 VOXBULK
```

**Body** — copy all:
```
Hi {{1}} 👋

Thanks for speaking with VOXBULK today.

When you're ready, tap *Send offer* below and we'll send your personal signup link 🎁

Tap *Stop* if you don't want further messages.

— VOXBULK Sales
```

**Sample variables (examples):**
| Variable | Sample |
|----------|--------|
| `{{1}}` | Alex |

**Footer** (optional):
```
Reply anytime · VOXBULK
```

**Buttons — Quick reply (2):**

| # | Button label (copy) | Sends when tapped |
|---|---------------------|-------------------|
| 1 | `🎁 Send offer` | Must contain "Send offer" |
| 2 | `🛑 Stop` | Must contain "Stop" |

> Keep the words **Send offer** and **Stop** in button labels so taps are recognised by VOXBULK.

---

## Template 2 — `voxbulk_sales_offer`

| Field | Value |
|-------|--------|
| **Name** | `voxbulk_sales_offer` |
| **Category** | Marketing |
| **Language** | English (UK) |

**Header** (optional · Text):
```
🎉 Your offer is ready
```

**Body** — copy all:
```
Hi {{1}} 👋

Your VOXBULK {{2}} is ready ✨

{{3}}

Tap *Start account* below to sign up — your offer applies automatically 🚀

Tap *Stop* if you don't want further messages.

— VOXBULK Sales
```

**Sample variables (examples):**
| Variable | Sample |
|----------|--------|
| `{{1}}` | Alex |
| `{{2}}` | 20 free survey contacts |
| `{{3}}` | Includes 20 survey contacts after signup. |

**Footer** (optional):
```
Secure signup · voxbulk.com
```

**Buttons:**

| # | Type | Button label | URL or payload |
|---|------|--------------|----------------|
| 1 | **URL** | `🚀 Start account` | `https://voxbulk.com/signin?{{1}}` |
| 2 | **Quick reply** | `🛑 Stop` | (tap sends button text) |

**URL button sample `{{1}}`:**
```
promo=SURVEY20
```

---

## Template 3 — `voxbulk_sales_followup`

| Field | Value |
|-------|--------|
| **Name** | `voxbulk_sales_followup` |
| **Category** | Marketing |
| **Language** | English (UK) |

**Header** (optional · Text):
```
⏰ Reminder
```

**Body** — copy all:
```
Hi {{1}} 👋

Your VOXBULK {{2}} is still waiting for you 🎁

Tap *Open offer* below to finish signup, or reply here if you need help 💬

Tap *Stop* to opt out.

— VOXBULK Sales
```

**Sample variables (examples):**
| Variable | Sample |
|----------|--------|
| `{{1}}` | Alex |
| `{{2}}` | 20 free survey contacts |

**Footer** (optional):
```
We're here if you need help
```

**Buttons:**

| # | Type | Button label | URL or payload |
|---|------|--------------|----------------|
| 1 | **URL** | `🔗 Open offer` | `https://voxbulk.com/signin?{{1}}` |
| 2 | **Quick reply** | `🛑 Stop` | (tap sends button text) |

**URL button sample `{{1}}`:**
```
promo=SURVEY20
```

---

## Template 4 — `voxbulk_sales_keyword_confirm`

| Field | Value |
|-------|--------|
| **Name** | `voxbulk_sales_keyword_confirm` |
| **Category** | Marketing |
| **Language** | English (UK) |

**Header** (optional · Text):
```
✅ As requested
```

**Body** — copy all:
```
Hi {{1}} 👋

As requested — your VOXBULK {{2}}:
{{3}}

Tap *Start account* below. Your offer applies automatically when you sign up 🚀

— VOXBULK Sales
```

**Sample variables (examples):**
| Variable | Sample |
|----------|--------|
| `{{1}}` | Alex |
| `{{2}}` | 20 free survey contacts |
| `{{3}}` | Includes 20 survey contacts after signup. |

**Footer** (optional):
```
Questions? Just reply here
```

**Buttons:**

| # | Type | Button label | URL |
|---|------|--------------|-----|
| 1 | **URL** | `🚀 Start account` | `https://voxbulk.com/signin?{{1}}` |

**URL button sample `{{1}}`:**
```
promo=SURVEY20
```

---

## Quick checklist

- [ ] All 4 names match exactly (`voxbulk_sales_*`)
- [ ] Language = **English (UK)** / `en_GB`
- [ ] Every `{{n}}` has a sample value filled in
- [ ] URL buttons use `https://voxbulk.com/signin?{{1}}` (not a short link)
- [ ] Quick-reply labels include **Send offer** / **Stop** wording
- [ ] Submit and wait for Meta approval (usually 24–48 h)

After approval, VOXBULK sends these automatically. Until then, plain-text fallback is used.
