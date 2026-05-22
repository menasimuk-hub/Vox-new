# Telnyx / Meta WhatsApp sales templates (with buttons)

Create these four templates in **Telnyx → Messaging → WhatsApp → Templates** (or Meta Business Manager). Names must match exactly — the API sends using these keys.

| VOXBULK key | Telnyx template name | Buttons |
|-------------|----------------------|---------|
| `sales_opt_in` | `voxbulk_sales_opt_in` | Quick reply **Send offer** · Quick reply **Stop** |
| `sales_offer` | `voxbulk_sales_offer` | URL **Start account** · Quick reply **Stop** |
| `sales_offer_followup` | `voxbulk_sales_followup` | URL **Open offer** · Quick reply **Stop** |
| `sales_offer_keyword_confirm` | `voxbulk_sales_keyword_confirm` | URL **Start account** |

Language: **English (UK)** (`en_GB`).

Quick-reply payloads must send the exact text **`SEND OFFER`** and **`STOP`** (inbound handler matches these).

---

## 1. `voxbulk_sales_opt_in`

**Category:** Marketing (or Utility if your Meta account requires it for opt-in)

**Body:**
```
Hi {{1}},

Thanks for speaking with VOXBULK today.

When you're ready, tap Send offer below and we'll send your personal signup link.

Tap Stop if you don't want further messages.

— VOXBULK Sales
```

**Buttons (Quick replies):**
1. Label: `Send offer` → sends text: `SEND OFFER`
2. Label: `Stop` → sends text: `STOP`

**API body variables:** `{{1}}` = first name

---

## 2. `voxbulk_sales_offer`

**Category:** Marketing

**Body:**
```
Hi {{1}},

Your VOXBULK {{2}} is ready:
{{3}}

Tap Start account below to sign up — your offer applies automatically.

Tap Stop if you don't want further messages.

— VOXBULK Sales
```

**Buttons:**
1. **URL** — Label: `Start account` — URL: `https://voxbulk.com/signin?{{1}}`
2. **Quick reply** — Label: `Stop` — sends: `STOP`

**API variables:**
- Body: `{{1}}` first name, `{{2}}` offer line, `{{3}}` offer summary
- URL button `{{1}}`: query string only, e.g. `promo=SALE1A2B3C`

---

## 3. `voxbulk_sales_followup`

**Category:** Marketing

**Body:**
```
Hi {{1}},

Your VOXBULK {{2}} is still waiting for you.

Tap Open offer below to finish signup, or reply here if you need help.

Tap Stop to opt out.

— VOXBULK Sales
```

**Buttons:**
1. **URL** — Label: `Open offer` — URL: `https://voxbulk.com/signin?{{1}}`
2. **Quick reply** — Label: `Stop` — sends: `STOP`

**API variables:**
- Body: `{{1}}` first name, `{{2}}` offer line
- URL button `{{1}}`: query string, e.g. `promo=SALE1A2B3C`

---

## 4. `voxbulk_sales_keyword_confirm`

**Category:** Marketing

**Body:**
```
Hi {{1}},

As requested — your VOXBULK {{2}}:
{{3}}

Tap Start account below. Your offer applies automatically when you sign up.

— VOXBULK Sales
```

**Buttons:**
1. **URL** — Label: `Start account` — URL: `https://voxbulk.com/signin?{{1}}`

**API variables:** same as `voxbulk_sales_offer`

---

## Fallback behaviour

If a Telnyx template is missing or not yet approved, VOXBULK sends the **plain-text body** from Admin → Marketing → WhatsApp templates (same copy, without interactive buttons).

After Meta approves templates, outbound sales messages use the Telnyx template API automatically.

---

## Deploy checklist

1. Create all four templates in Telnyx/Meta and wait for approval.
2. On VPS: `alembic upgrade head` (migration `0063_sales_wa_button_templates`).
3. Rebuild admin if you pulled frontend changes.
4. Send a test lukewarm call → opt-in message should show **Send offer** / **Stop** buttons.
